const state = { file: null, result: null };
// Запасной список на случай, если /scenario недоступен; основной берётся из config/keywords.yaml.
let keywords = ["мойка", "кузов", "салон", "запись"];

const $ = (id) => document.getElementById(id);
const fileInput = $("audio-file");
const dropZone = $("drop-zone");
const filePreview = $("file-preview");
const fileName = $("file-name");
const fileMeta = $("file-meta");
const transcribeButton = $("transcribe-button");
const errorBox = $("error-box");
const sampleSelect = $("sample-select");
const resultSection = $("result-section");
const transcript = $("transcript");
const foundKeywords = $("found-keywords");
const emptyKeywords = $("empty-keywords");
const latency = $("latency");
const segmentCount = $("segment-count");
const jsonOutput = $("json-output");

function renderKeywordChips() {
  $("keyword-list").innerHTML = keywords.map(k => `<span class="keyword-chip">${escapeHtml(k)}</span>`).join("");
}

async function loadScenario() {
  try {
    const response = await fetch("/scenario", { cache: "no-store" });
    if (!response.ok) throw new Error();
    const data = await response.json();
    if (Array.isArray(data.keywords) && data.keywords.length) keywords = data.keywords;
  } catch {
    /* остаёмся на запасном списке */
  }
  renderKeywordChips();
}

function pluralMatches(n) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "совпадение";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "совпадения";
  return "совпадений";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

function setError(message = "") {
  errorBox.textContent = message;
  errorBox.classList.toggle("hidden", !message);
}

function setFile(file) {
  setError("");
  if (!file) return;
  state.file = file;
  fileName.textContent = file.name;
  fileMeta.textContent = `${formatBytes(file.size)} · ${file.type || "аудиофайл"}`;
  filePreview.classList.remove("hidden");
  transcribeButton.disabled = false;
  sampleSelect.value = "";
}

function clearFile() {
  state.file = null;
  fileInput.value = "";
  filePreview.classList.add("hidden");
  transcribeButton.disabled = true;
  setError("");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

async function checkHealth() {
  const dot = $("health-dot");
  const text = $("health-text");
  try {
    const response = await fetch("/health", { cache: "no-store" });
    if (!response.ok) throw new Error();
    const ready = await fetch("/ready", { cache: "no-store" }).then((r) => r.json()).catch(() => null);
    if (ready && ready.error) {
      dot.className = "status-dot is-error";
      text.textContent = "Модель не загрузилась";
    } else if (ready && !ready.model_loaded) {
      // Холодный старт на бесплатном хостинге: модель ещё грузится — спрашиваем снова.
      dot.className = "status-dot is-loading";
      text.textContent = "Модель загружается…";
      setTimeout(checkHealth, 3000);
    } else {
      dot.className = "status-dot is-ok";
      text.textContent = "Сервис работает";
    }
  } catch {
    dot.className = "status-dot is-error";
    text.textContent = "Сервис недоступен";
    setTimeout(checkHealth, 5000);
  }
}

async function loadSample(filename) {
  try {
    setError("");
    const response = await fetch(`/samples/${encodeURIComponent(filename)}`);
    if (!response.ok) throw new Error("Не удалось загрузить sample-файл.");
    const blob = await response.blob();
    setFile(new File([blob], filename, { type: blob.type || "audio/wav" }));
  } catch (error) {
    setError(error.message);
    sampleSelect.value = "";
  }
}

function renderResult(data) {
  state.result = data;
  resultSection.classList.remove("hidden");
  transcript.textContent = data.text || "Речь не распознана.";
  latency.textContent = `${data.latency_ms ?? "—"} мс`;
  segmentCount.textContent = `${(data.segments || []).length} сегм.`;
  jsonOutput.textContent = JSON.stringify(data, null, 2);

  foundKeywords.innerHTML = "";
  const matches = data.keywords_found || [];
  emptyKeywords.classList.toggle("hidden", matches.length > 0);
  for (const item of matches) {
    const card = document.createElement("div");
    card.className = "found-keyword";
    card.innerHTML = `<strong>${escapeHtml(item.keyword)}</strong><span>${item.count} ${pluralMatches(item.count)}</span>`;
    foundKeywords.appendChild(card);
  }
  resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function transcribe() {
  if (!state.file) return;
  setError("");
  transcribeButton.disabled = true;
  transcribeButton.classList.add("loading");

  const form = new FormData();
  form.append("file", state.file);

  try {
    const response = await fetch("/transcribe", { method: "POST", body: form });
    const data = await response.json().catch(() => ({ detail: "Сервер вернул некорректный ответ." }));
    if (!response.ok) throw new Error(data.detail || `Ошибка HTTP ${response.status}`);
    renderResult(data);
  } catch (error) {
    setError(error.message || "Не удалось обработать аудио.");
  } finally {
    transcribeButton.disabled = !state.file;
    transcribeButton.classList.remove("loading");
  }
}

fileInput.addEventListener("change", (event) => setFile(event.target.files?.[0] || null));
$("remove-file").addEventListener("click", clearFile);
sampleSelect.addEventListener("change", (event) => event.target.value && loadSample(event.target.value));
transcribeButton.addEventListener("click", transcribe);

for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.add("dragover"); });
}
for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.remove("dragover"); });
}
dropZone.addEventListener("drop", (event) => setFile(event.dataTransfer.files?.[0] || null));

$("copy-json").addEventListener("click", async () => {
  if (!state.result) return;
  try {
    await navigator.clipboard.writeText(JSON.stringify(state.result, null, 2));
    const button = $("copy-json");
    const original = button.textContent;
    button.textContent = "Скопировано";
    setTimeout(() => { button.textContent = original; }, 1400);
  } catch {
    setError("Браузер не разрешил копирование JSON.");
  }
});

renderKeywordChips();
loadScenario();
checkHealth();
