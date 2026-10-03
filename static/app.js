"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  fileInput: $("audio-file"), dropZone: $("drop-zone"), player: $("player"),
  fileName: $("file-name"), fileMeta: $("file-meta"), removeFile: $("remove-file"),
  playButton: $("play-button"), wave: $("wave"), timeCurrent: $("time-current"), timeTotal: $("time-total"),
  go: $("transcribe-button"), samples: $("samples"), keywordList: $("keyword-list"),
  percent: $("progress-percent"), bar: $("progress-bar"), stage: $("progress-stage"),
  transcript: $("transcript"), latency: $("latency"), errorBox: $("error-box"),
  healthDot: $("health-dot"), healthText: $("health-text"),
};
const states = { idle: $("state-idle"), progress: $("state-progress"), result: $("state-result"), error: $("state-error") };

// Запасной список на случай, если /scenario недоступен; основной берётся из config/keywords.yaml.
let keywords = ["мойка", "кузов", "салон", "запись"];
const app = { file: null, busy: false, fileToken: 0 };

/* ---------------------------------------------------------------- состояния */
function showState(name) {
  for (const [key, node] of Object.entries(states)) node.classList.toggle("is-active", key === name);
}

function setError(message) {
  els.errorBox.textContent = message;
  showState("error");
}

/* -------------------------------------------------------- ключевые слова */
function renderChips(found = []) {
  const counts = new Map(found.map((item) => [item.keyword, item.count]));
  els.keywordList.innerHTML = "";
  for (const word of keywords) {
    const chip = document.createElement("li");
    chip.className = "chip" + (counts.has(word) ? " found" : "");
    chip.append(word);
    const badge = document.createElement("span");
    badge.className = "count";
    badge.textContent = counts.get(word) ?? "";
    chip.append(badge);
    els.keywordList.append(chip);
  }
}

async function loadScenario() {
  try {
    const response = await fetch("/scenario", { cache: "no-store" });
    if (!response.ok) throw new Error();
    const data = await response.json();
    if (Array.isArray(data.keywords) && data.keywords.length) keywords = data.keywords;
  } catch { /* остаёмся на запасном списке */ }
  renderChips();
}

// Те же правила, что на сервере (app/keywords.py): поиск по основе слова.
const normalize = (text) => text.toLowerCase().replaceAll("ё", "е");
function stemOf(word) {
  const base = normalize(word).replace(/[аяуюыиеоэьй]+$/u, "");
  return base.length >= 4 ? base : null;
}
function matchesKeyword(token, word) {
  const t = normalize(token);
  const stem = stemOf(word);
  return stem ? t.startsWith(stem) : t === normalize(word);
}

function renderTranscript(text) {
  els.transcript.textContent = "";
  // \p{L} — любые буквы, в том числе кириллица (обычный \w её не знает)
  for (const part of text.split(/([\p{L}\p{N}-]+)/u)) {
    if (!part) continue;
    if (/^[\p{L}\p{N}-]+$/u.test(part) && keywords.some((word) => matchesKeyword(part, word))) {
      const mark = document.createElement("mark");
      mark.textContent = part;
      els.transcript.append(mark);
    } else {
      els.transcript.append(part);
    }
  }
}

/* --------------------------------------------------------------- здоровье */
async function checkHealth() {
  const set = (cls, text) => { els.healthDot.className = `dot ${cls}`; els.healthText.textContent = text; };
  try {
    const response = await fetch("/health", { cache: "no-store" });
    if (!response.ok) throw new Error();
    const ready = await fetch("/ready", { cache: "no-store" }).then((r) => r.json()).catch(() => null);
    if (ready?.error) {
      set("is-error", "Модель не загрузилась");
    } else if (ready && !ready.model_loaded) {
      // Холодный старт на бесплатном хостинге: модель ещё грузится — спрашиваем снова.
      set("is-loading", "Модель загружается…");
      setTimeout(checkHealth, 3000);
    } else {
      set("is-ok", "Сервис работает");
    }
  } catch {
    set("is-error", "Сервис недоступен");
    setTimeout(checkHealth, 5000);
  }
}

/* ------------------------------------------------------------------ плеер */
const BARS = 64;
const audio = new Audio();
audio.preload = "auto";
const player = { url: null, duration: 0, lastOn: -1, raf: 0, dragging: false };

const fmtTime = (s) => {
  if (!Number.isFinite(s) || s < 0) s = 0;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
};
const fmtBytes = (n) => (n < 1024 ? `${n} Б` : n < 1048576 ? `${(n / 1024).toFixed(1)} КБ` : `${(n / 1048576).toFixed(1)} МБ`);
const totalDuration = () => (Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : player.duration);

function buildBars(heights) {
  els.wave.textContent = "";
  for (let i = 0; i < BARS; i++) {
    const bar = document.createElement("span");
    bar.className = "bar";
    bar.style.height = `${heights[i]}%`;
    els.wave.append(bar);
  }
  player.lastOn = -1;
  paintProgress();
}

async function drawWave(file, token) {
  // сначала ровная «заготовка», затем настоящая форма звука
  buildBars(Array.from({ length: BARS }, (_, i) => 22 + 14 * Math.sin(i * 0.7)));
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const decoded = await ctx.decodeAudioData(await file.arrayBuffer());
    ctx.close();
    if (token !== app.fileToken) return;
    player.duration = decoded.duration;
    const data = decoded.getChannelData(0);
    const step = Math.max(1, Math.floor(data.length / BARS));
    const peaks = Array.from({ length: BARS }, (_, i) => {
      let max = 0;
      for (let j = i * step; j < Math.min(data.length, (i + 1) * step); j += 8) max = Math.max(max, Math.abs(data[j]));
      return max;
    });
    const top = Math.max(...peaks) || 1;
    buildBars(peaks.map((p) => 14 + 86 * Math.pow(p / top, 0.7)));
    els.timeTotal.textContent = fmtTime(totalDuration());
  } catch { /* формат не разобрать браузером — остаётся заготовка, плеер всё равно работает */ }
}

function paintProgress() {
  const total = totalDuration();
  const fraction = total ? Math.min(1, audio.currentTime / total) : 0;
  const on = Math.floor(fraction * BARS);
  if (on !== player.lastOn) {
    const bars = els.wave.children;
    for (let i = 0; i < bars.length; i++) bars[i].classList.toggle("on", i < on);
    player.lastOn = on;
  }
  els.timeCurrent.textContent = fmtTime(audio.currentTime);
  els.wave.setAttribute("aria-valuenow", String(Math.round(fraction * 100)));
}

function playLoop() {
  paintProgress();
  if (!audio.paused) player.raf = requestAnimationFrame(playLoop);
}

function togglePlay() {
  if (!app.file) return;
  if (audio.paused) audio.play().catch(() => setError("Браузер не смог воспроизвести этот файл."));
  else audio.pause();
}

function seekTo(clientX) {
  const total = totalDuration();
  if (!total) return;
  const rect = els.wave.getBoundingClientRect();
  audio.currentTime = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)) * total;
  paintProgress();
}

audio.addEventListener("play", () => { els.playButton.classList.add("is-playing"); cancelAnimationFrame(player.raf); playLoop(); });
audio.addEventListener("pause", () => { els.playButton.classList.remove("is-playing"); paintProgress(); });
audio.addEventListener("ended", () => { audio.currentTime = 0; els.playButton.classList.remove("is-playing"); paintProgress(); });
audio.addEventListener("loadedmetadata", () => { els.timeTotal.textContent = fmtTime(totalDuration()); });
els.playButton.addEventListener("click", togglePlay);
els.wave.addEventListener("pointerdown", (event) => { player.dragging = true; els.wave.setPointerCapture(event.pointerId); seekTo(event.clientX); });
els.wave.addEventListener("pointermove", (event) => { if (player.dragging) seekTo(event.clientX); });
for (const type of ["pointerup", "pointercancel"]) els.wave.addEventListener(type, () => { player.dragging = false; });
els.wave.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight") { audio.currentTime = Math.min(totalDuration(), audio.currentTime + 2); paintProgress(); event.preventDefault(); }
  if (event.key === "ArrowLeft") { audio.currentTime = Math.max(0, audio.currentTime - 2); paintProgress(); event.preventDefault(); }
  if (event.key === " " || event.key === "Enter") { togglePlay(); event.preventDefault(); }
});

/* ------------------------------------------------------------------ файл */
function setFile(file, sampleName = "") {
  if (!file) return;
  audio.pause();
  if (player.url) URL.revokeObjectURL(player.url);
  app.file = file;
  app.fileToken += 1;
  player.duration = 0;
  player.url = URL.createObjectURL(file);
  audio.src = player.url;
  els.fileName.textContent = file.name;
  els.fileMeta.textContent = fmtBytes(file.size);
  els.timeCurrent.textContent = "0:00";
  els.timeTotal.textContent = "0:00";
  els.dropZone.classList.remove("is-active");
  els.player.classList.add("is-active");
  els.go.disabled = app.busy;
  for (const button of els.samples.children) button.classList.toggle("is-current", button.dataset.file === sampleName);
  renderChips();
  showState("idle");
  drawWave(file, app.fileToken);
}

function clearFile() {
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  if (player.url) URL.revokeObjectURL(player.url);
  player.url = null;
  app.file = null;
  app.fileToken += 1;
  els.fileInput.value = "";
  els.player.classList.remove("is-active");
  els.dropZone.classList.add("is-active");
  els.go.disabled = true;
  for (const button of els.samples.children) button.classList.remove("is-current");
  renderChips();
  showState("idle");
}

async function loadSample(filename) {
  try {
    const response = await fetch(`/samples/${encodeURIComponent(filename)}`);
    if (!response.ok) throw new Error("Не удалось загрузить пример.");
    const blob = await response.blob();
    setFile(new File([blob], filename, { type: blob.type || "audio/wav" }), filename);
  } catch (error) {
    setError(error.message);
  }
}

els.fileInput.addEventListener("change", (event) => setFile(event.target.files?.[0]));
els.removeFile.addEventListener("click", clearFile);
els.samples.addEventListener("click", (event) => {
  const button = event.target.closest(".sample");
  if (button && !app.busy) loadSample(button.dataset.file);
});
for (const name of ["dragenter", "dragover"]) els.dropZone.addEventListener(name, (e) => { e.preventDefault(); els.dropZone.classList.add("dragover"); });
for (const name of ["dragleave", "drop"]) els.dropZone.addEventListener(name, (e) => { e.preventDefault(); els.dropZone.classList.remove("dragover"); });
els.dropZone.addEventListener("drop", (event) => setFile(event.dataTransfer.files?.[0]));

/* -------------------------------------------------------------- прогресс */
const UPLOAD_SHARE = 15;   // загрузка файла занимает первые 15 % шкалы
const CREEP_LIMIT = 88;    // пока сервер считает, шкала ползёт не дальше этого значения
const prog = { shown: 0, target: 0, phase: "idle", raf: 0, last: 0, poller: 0 };

function renderProgress() {
  const value = Math.round(prog.shown);
  els.bar.style.width = `${prog.shown}%`;
  els.percent.textContent = `${value}%`;
  els.percent.setAttribute("aria-valuenow", String(value));
}

function progressFrame(now) {
  if (prog.phase === "idle") return;
  const dt = Math.min(0.1, (now - prog.last) / 1000 || 0.016);
  prog.last = now;
  if (prog.phase === "server") {
    // Whisper отдаёт сегменты только по готовности, поэтому между реальными
    // отметками шкала плавно ползёт вперёд — но не дальше лимита.
    prog.target = Math.max(prog.target, Math.min(CREEP_LIMIT, prog.shown + (CREEP_LIMIT - prog.shown) * 0.06 * dt));
  }
  const rate = prog.phase === "done" ? 14 : 6;
  prog.shown += (prog.target - prog.shown) * (1 - Math.exp(-dt * rate));
  if (Math.abs(prog.target - prog.shown) < 0.05) prog.shown = prog.target;
  if (prog.phase === "done" && prog.shown >= 99.5) els.stage.textContent = "Готово";
  renderProgress();
  prog.raf = requestAnimationFrame(progressFrame);
}

function startProgress() {
  Object.assign(prog, { shown: 0, target: 0, phase: "upload", last: performance.now() });
  els.stage.textContent = "Загрузка файла…";
  renderProgress();
  showState("progress");
  cancelAnimationFrame(prog.raf);
  prog.raf = requestAnimationFrame(progressFrame);
}

function stopProgress() {
  clearInterval(prog.poller);
  cancelAnimationFrame(prog.raf);
  prog.phase = "idle";
}

async function finishProgress() {
  clearInterval(prog.poller);
  prog.phase = "done";
  prog.target = 100;
  els.stage.textContent = "Завершаем…";
  await new Promise((resolve) => setTimeout(resolve, 900));  // дать увидеть 100 %
  stopProgress();
}

function beginServerPhase(jobId) {
  prog.phase = "server";
  prog.target = Math.max(prog.target, UPLOAD_SHARE);
  els.stage.textContent = "Подготовка аудио…";
  clearInterval(prog.poller);
  prog.poller = setInterval(async () => {
    try {
      const response = await fetch(`/progress/${jobId}`, { cache: "no-store" });
      if (!response.ok || prog.phase !== "server") return;
      const info = await response.json();
      if (info.stage === "waiting" || info.stage === "error") return;
      prog.target = Math.max(prog.target, UPLOAD_SHARE + (100 - UPLOAD_SHARE) * (info.percent / 100));
      els.stage.textContent = `${info.label}…`;
    } catch { /* следующий опрос исправит */ }
  }, 350);
}

const makeJobId = () => (window.crypto?.randomUUID ? crypto.randomUUID() : `job-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`);

function sendFile(file, jobId) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/transcribe");
    xhr.setRequestHeader("X-Job-Id", jobId);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && prog.phase === "upload") prog.target = UPLOAD_SHARE * (event.loaded / event.total);
    };
    xhr.upload.onload = () => beginServerPhase(jobId);
    xhr.onload = () => {
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { data = { detail: "Сервер вернул некорректный ответ." }; }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data });
    };
    xhr.onerror = () => reject(new Error("Нет связи с сервером. Если он на бесплатном хостинге, подождите минуту и повторите."));
    xhr.send(form);  // без таймаута: если распознаванию нужно больше времени, мы его ждём
  });
}

function setBusy(busy) {
  app.busy = busy;
  els.go.disabled = busy || !app.file;
  els.go.classList.toggle("busy", busy);
  els.go.textContent = busy ? "Обрабатываем…" : "Распознать";
  els.samples.classList.toggle("is-locked", busy);
}

async function transcribe() {
  if (!app.file || app.busy) return;
  audio.pause();
  setBusy(true);
  renderChips();
  startProgress();
  try {
    const { ok, status, data } = await sendFile(app.file, makeJobId());
    if (!ok) throw new Error(data.detail || `Ошибка HTTP ${status}`);
    await finishProgress();
    renderChips(data.keywords_found || []);
    renderTranscript(data.text || "Речь не распознана.");
    els.latency.textContent = data.latency_ms ? `Обработано за ${(data.latency_ms / 1000).toFixed(1).replace(".", ",")} с` : "";
    showState("result");
  } catch (error) {
    stopProgress();
    setError(error.message || "Не удалось обработать аудио.");
  } finally {
    setBusy(false);
  }
}
els.go.addEventListener("click", transcribe);

/* ------------------------------------------------------------------ старт */
renderChips();
loadScenario();
checkHealth();
