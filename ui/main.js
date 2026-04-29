// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

import {
  deleteTake,
  getBank,
  getBanks,
  getHealth,
  getReference,
  getReferenceSources,
  getTakeWav,
  postBank,
  postExport,
  postTake,
  putConfig,
  putState,
} from "/ui/api.js";
import {
  isPlaying,
  playBuffer,
  renderWaveform,
  requestMic,
  startMeter,
  stopPlayback,
} from "/ui/audio.js";
import { isRecording, startRecording, stopRecording } from "/ui/record.js";

const banner = document.getElementById("health-banner");
const recordButton = document.getElementById("record");
const bankSelect = document.getElementById("bank-select");
const privacyBadge = document.getElementById("privacy-badge");
const phonemeList = document.getElementById("phoneme-list");
const phonemeDetail = document.getElementById("phoneme-detail");
const micGrantButton = document.getElementById("mic-grant");
const micDeviceLabel = document.getElementById("mic-device");
const micErrorBanner = document.getElementById("mic-error");
const meterCanvas = document.getElementById("meter-canvas");
const exportButton = document.getElementById("export-button");
const exportModal = document.getElementById("export-modal");
const exportModalBody = document.getElementById("export-modal-body");
const gitignoreBanner = document.getElementById("gitignore-banner");
const privacyModal = document.getElementById("privacy-modal");
const privacyModalTitle = document.getElementById("privacy-modal-title");
const privacyModalBody = document.getElementById("privacy-modal-body");
const privacyModalActions = document.getElementById("privacy-modal-actions");
const newBankButton = document.getElementById("new-bank-button");
const newBankModal = document.getElementById("new-bank-modal");
const newBankForm = document.getElementById("new-bank-form");
const newBankError = document.getElementById("new-bank-error");
const newBankInventorySelect = document.getElementById("new-bank-inventory");
const newBankSubmit = document.getElementById("new-bank-submit");

const METER_DB_FLOOR = -60;
const METER_DECAY_DB_PER_SEC = 40;
const METER_CLIP_THRESHOLD_DB = -1;

const DEFAULT_REFERENCE_SOURCES = [
  { id: "auto", label: "Auto — PolyU if present, else Vocabulary.com" },
  { id: "polyu", label: "PolyU ELC (HK)" },
  { id: "vocabulary", label: "Vocabulary.com" },
];

let referenceSourceList = DEFAULT_REFERENCE_SOURCES;

let currentBank = null;
let selectedPhonemeId = null;
let selectedTakeId = null;
let pendingDeleteTakeId = null;
let playingTakeId = null;
let meterPeakHoldDb = METER_DB_FLOOR;
let meterLastTimestamp = null;
let micStream = null;
let toolsOk = false;
let activeRecordingPhonemeId = null;
let savingTake = false;
const toastElement = ensureToast();

async function init() {
  renderHealth(await safeGetHealth());
  try {
    const { sources } = await getReferenceSources();
    if (Array.isArray(sources) && sources.length > 0) referenceSourceList = sources;
  } catch {
    // keep default list
  }
  await loadBanks();
  window.addEventListener("keydown", handleKeyDown);
  bankSelect.addEventListener("change", () => loadBank(bankSelect.value));
  micGrantButton.addEventListener("click", grantMicAndStartMeter);
  recordButton.addEventListener("click", toggleRecording);
  phonemeDetail.addEventListener("click", handleDetailClick);
  exportButton.addEventListener("click", runExport);
  exportModal.addEventListener("click", (event) => {
    if (event.target?.dataset?.action === "close-modal") closeExportModal();
  });
  privacyBadge.addEventListener("click", openPrivacyFlipModal);
  privacyModal.addEventListener("click", handlePrivacyModalClick);
  gitignoreBanner.addEventListener("click", handleGitignoreBannerClick);
  newBankButton.addEventListener("click", openNewBankModal);
  newBankModal.addEventListener("click", (event) => {
    if (event.target?.dataset?.action === "close-new-bank-modal") closeNewBankModal();
  });
  newBankForm.addEventListener("submit", submitNewBank);
  phonemeDetail.addEventListener("change", (e) => {
    if (e.target?.id === "ref-source") {
      localStorage.setItem("reference_source", e.target.value);
    }
  });
}

async function safeGetHealth() {
  try {
    return await getHealth();
  } catch (err) {
    return { error: err.message };
  }
}

function renderHealth(body) {
  banner.classList.remove(
    "health-banner--unknown",
    "health-banner--ready",
    "health-banner--missing",
  );

  if (body?.error) {
    banner.classList.add("health-banner--missing");
    banner.textContent = `Health check failed: ${body.error}`;
    toolsOk = false;
    updateRecordButton();
    return;
  }

  const missing = [];
  if (!body.tools?.ffmpeg) missing.push("ffmpeg");
  // espeak-ng is optional (reference is file-based)

  if (missing.length === 0) {
    banner.classList.add("health-banner--ready");
    banner.textContent = `Ready · v${body.version}`;
    toolsOk = true;
  } else {
    banner.classList.add("health-banner--missing");
    banner.textContent = `Missing: ${missing.join(", ")} — brew install ${missing.join(" ")}`;
    toolsOk = false;
  }
  updateRecordButton();
}

async function loadBanks() {
  try {
    const { banks } = await getBanks();
    if (banks.length === 0) {
      bankSelect.innerHTML = '<option value="">No banks</option>';
      bankSelect.disabled = true;
      renderEmpty("No banks found. Create one in banks/<id>/config.json.");
      return;
    }
    bankSelect.innerHTML = banks
      .map((b) => `<option value="${b.id}">${escapeHtml(b.name)}</option>`)
      .join("");
    bankSelect.disabled = false;
    const last = localStorage.getItem("last_bank_id");
    const pick = banks.find((b) => b.id === last) ? last : banks[0].id;
    bankSelect.value = pick;
    await loadBank(pick);
  } catch (err) {
    renderEmpty(`Failed to load banks: ${err.message}`);
  }
}

async function loadBank(id) {
  try {
    const bank = await getBank(id);
    currentBank = bank;
    localStorage.setItem("last_bank_id", id);
    renderPrivacyBadge(bank.config.privacy);
    renderGitignoreBanner(bank.gitignore);
    renderPhonemeList(bank);
    const firstId = bank.config.phonemes[0]?.id ?? null;
    const lastPhonemeId = bank.state.last_phoneme_id;
    const initial = bank.config.phonemes.find((p) => p.id === lastPhonemeId)
      ? lastPhonemeId
      : firstId;
    selectPhoneme(initial);
  } catch (err) {
    currentBank = null;
    renderEmpty(`Failed to load bank ${id}: ${err.message}`);
  }
}

function renderGitignoreBanner(status) {
  if (!status || status.status === "ok") {
    gitignoreBanner.hidden = true;
    gitignoreBanner.textContent = "";
    return;
  }
  const label =
    status.status === "missing"
      ? "Missing per-bank <code>.gitignore</code>"
      : "<code>.gitignore</code> drift detected";
  gitignoreBanner.hidden = false;
  gitignoreBanner.innerHTML = `
    <div class="gitignore-banner__text">
      <strong>${label}</strong>
      <p>Expected: <code>${escapeHtml(status.expected || "(empty)")}</code></p>
      <p>Current: <code>${escapeHtml(status.current || "(absent)")}</code></p>
    </div>
    <button type="button" class="gitignore-banner__sync" data-action="sync-gitignore">
      Sync
    </button>
  `;
}

async function handleGitignoreBannerClick(event) {
  if (event.target?.dataset?.action !== "sync-gitignore") return;
  if (!currentBank) return;
  const bankId = bankSelect.value;
  event.target.disabled = true;
  event.target.textContent = "Syncing…";
  try {
    const updated = await putConfig(bankId, {});
    currentBank.config = updated.config;
    currentBank.gitignore = updated.gitignore;
    renderGitignoreBanner(updated.gitignore);
    showToast("Synced .gitignore", "success");
  } catch (err) {
    event.target.disabled = false;
    event.target.textContent = "Sync";
    showToast(`Sync failed: ${err.message}`, "error");
  }
}

function renderPrivacyBadge(privacy) {
  privacyBadge.hidden = false;
  privacyBadge.classList.remove(
    "privacy-badge--public",
    "privacy-badge--private",
    "privacy-badge--unknown",
  );
  privacyBadge.classList.add(
    privacy === "public" ? "privacy-badge--public" : "privacy-badge--private",
  );
  privacyBadge.textContent = privacy === "public" ? "Public" : "Private";
}

function renderPhonemeList(bank) {
  phonemeList.innerHTML = "";
  for (const phoneme of bank.config.phonemes) {
    const glyph = statusGlyph(phoneme.id, bank.state);
    const li = document.createElement("li");
    li.className = "phoneme-item";
    li.dataset.phonemeId = phoneme.id;
    li.innerHTML = `
      <span class="phoneme-item__glyph" aria-hidden="true">${glyph}</span>
      <span class="phoneme-item__ipa">${escapeHtml(phoneme.ipa)}</span>
      <span class="phoneme-item__example">${escapeHtml(phoneme.example ?? "")}</span>
    `;
    li.addEventListener("click", () => selectPhoneme(phoneme.id));
    phonemeList.appendChild(li);
  }
}

function statusGlyph(phonemeId, state) {
  const entry = state?.phonemes?.[phonemeId];
  if (!entry || !entry.takes || entry.takes.length === 0) return "○";
  if (entry.keeper_take) return "✓";
  return "●";
}

function selectPhoneme(id, { preferTakeId } = {}) {
  if (playingTakeId) {
    stopPlayback();
    playingTakeId = null;
  }
  selectedPhonemeId = id;
  pendingDeleteTakeId = null;
  for (const item of phonemeList.querySelectorAll(".phoneme-item")) {
    item.classList.toggle(
      "phoneme-item--selected",
      item.dataset.phonemeId === id,
    );
  }
  if (!id || !currentBank) {
    selectedTakeId = null;
    renderEmpty("Select a phoneme to begin.");
    return;
  }
  selectedTakeId = preferTakeId ?? defaultTakeForPhoneme(id);
  const phoneme = currentBank.config.phonemes.find((p) => p.id === id);
  if (phoneme) {
    renderDetail(phoneme);
    paintWaveformForSelectedTake();
  }
}

function defaultTakeForPhoneme(phonemeId) {
  const ph = currentBank?.state?.phonemes?.[phonemeId] ?? {};
  if (ph.keeper_take) return ph.keeper_take;
  const takes = ph.takes ?? [];
  return takes.length > 0 ? takes[takes.length - 1].id : null;
}

function selectTake(takeId) {
  if (playingTakeId) {
    stopPlayback();
    playingTakeId = null;
  }
  selectedTakeId = takeId;
  pendingDeleteTakeId = null;
  if (selectedPhonemeId) {
    const phoneme = currentBank.config.phonemes.find((p) => p.id === selectedPhonemeId);
    if (phoneme) {
      renderDetail(phoneme);
      paintWaveformForSelectedTake();
    }
  }
}

function renderDetail(phoneme) {
  const phonemeState = currentBank?.state?.phonemes?.[phoneme.id] ?? {};
  const takes = phonemeState.takes ?? [];
  const keeperTakeId = phonemeState.keeper_take ?? null;
  const storedRef = localStorage.getItem("reference_source") || "auto";
  const refOpts = referenceSourceList
    .map((s) => {
      const sel = s.id === storedRef ? " selected" : "";
      return `<option value="${escapeHtml(s.id)}"${sel}>${escapeHtml(s.label)}</option>`;
    })
    .join("");
  phonemeDetail.innerHTML = `
    <div class="phoneme-detail__header">
      <span class="phoneme-detail__ipa">${escapeHtml(phoneme.ipa)}</span>
      <span class="phoneme-detail__example">${escapeHtml(phoneme.example ?? "")}</span>
      <div class="reference-controls">
        <label class="ref-source-label">Reference
          <select id="ref-source" class="ref-source" aria-label="Reference clip source">${refOpts}</select>
        </label>
        <button class="reference-btn" data-action="play-reference" type="button" aria-label="Play reference audio (G)">
          ▶ <kbd>G</kbd>
        </button>
      </div>
    </div>
    <p id="reference-attribution" class="reference-attribution" hidden></p>
    <dl class="phoneme-detail__meta">
      <dt>Id</dt><dd>${escapeHtml(phoneme.id)}</dd>
      <dt>Category</dt><dd>${escapeHtml(phoneme.category ?? "—")}</dd>
      <dt>Loopable</dt><dd>${phoneme.loopable ? "yes" : "no"}</dd>
    </dl>
    <h2 class="takes-heading">Takes (${takes.length})</h2>
    ${takes.length === 0
      ? '<p class="placeholder">No takes yet. Press R (or click Record) to record one.</p>'
      : `<ul class="takes-list">${takes.map((t) => renderTakeRow(t, keeperTakeId)).join("")}</ul>
         <canvas class="take-waveform" height="80" aria-label="Waveform of selected take"></canvas>`}
  `;
}

function renderTakeRow(take, keeperTakeId) {
  if (pendingDeleteTakeId === take.id) {
    return `
      <li class="takes-item takes-item--pending-delete" data-take-id="${escapeHtml(take.id)}">
        <span class="takes-item__confirm-message">Delete ${escapeHtml(take.id)}?</span>
        <div class="takes-item__confirm-actions">
          <button class="takes-btn" data-action="cancel-delete" type="button">Cancel</button>
          <button class="takes-btn takes-btn--danger" data-action="confirm-delete" type="button">Delete</button>
        </div>
      </li>
    `;
  }

  const isKeeper = take.id === keeperTakeId;
  const isSelected = take.id === selectedTakeId;
  const isThisPlaying = take.id === playingTakeId;
  const playGlyph = isThisPlaying ? "■" : "▶";
  const classes = [
    "takes-item",
    isKeeper ? "takes-item--keeper" : "",
    isSelected ? "takes-item--selected" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return `
    <li class="${classes}" data-take-id="${escapeHtml(take.id)}">
      <button class="takes-btn takes-btn--play" data-action="play" type="button" aria-label="Play ${escapeHtml(take.id)}">${playGlyph}</button>
      <span class="takes-item__id">${escapeHtml(take.id)}</span>
      <span class="takes-item__duration">${take.duration_ms} ms</span>
      <span class="takes-item__peak">peak ${formatDb(take.peak_db)}</span>
      <span class="takes-item__rms">rms ${formatDb(take.rms_db)}</span>
      <button class="takes-btn takes-btn--keeper ${isKeeper ? "takes-btn--keeper-on" : ""}" data-action="keeper" type="button" aria-pressed="${isKeeper}">${isKeeper ? "★ Keeper" : "☆ Keeper"}</button>
      <button class="takes-btn takes-btn--delete" data-action="delete" type="button" aria-label="Delete ${escapeHtml(take.id)}">🗑</button>
    </li>
  `;
}

function formatDb(db) {
  const sign = db > 0 ? "+" : "";
  return `${sign}${Number(db).toFixed(1)} dB`;
}

function renderEmpty(message) {
  phonemeList.innerHTML = "";
  phonemeDetail.innerHTML = `<p class="placeholder">${escapeHtml(message)}</p>`;
}

function handleKeyDown(event) {
  const tag = document.activeElement?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

  // Export modal acts as a modal: Escape closes it, every other
  // shortcut is ignored while it's open.
  if (!exportModal.hidden) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeExportModal();
    }
    return;
  }

  // Privacy flip modal — Escape closes; all other shortcuts suppressed.
  // Typing inside the attribution textbox is already handled by the
  // INPUT short-circuit above.
  if (!privacyModal.hidden) {
    if (event.key === "Escape") {
      event.preventDefault();
      closePrivacyModal();
    }
    return;
  }

  // New-bank modal — Escape closes; every other shortcut suppressed.
  if (!newBankModal.hidden) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeNewBankModal();
    }
    return;
  }

  // Delete-confirm acts as a modal: only Enter confirms and Escape cancels;
  // every other shortcut is ignored until the user resolves it.
  if (pendingDeleteTakeId) {
    if (event.key === "Enter") {
      event.preventDefault();
      doDelete(pendingDeleteTakeId);
    } else if (event.key === "Escape") {
      event.preventDefault();
      hideDeleteConfirm();
    }
    return;
  }

  if (
    tag === "BUTTON" &&
    (event.key === "Enter" || event.key === " " || event.key === "Backspace")
  ) {
    // Let the focused button handle these keys natively.
    return;
  }

  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    if (!currentBank?.config.phonemes?.length) return;
    event.preventDefault();
    const ids = currentBank.config.phonemes.map((p) => p.id);
    const idx = Math.max(0, ids.indexOf(selectedPhonemeId));
    const delta = event.key === "ArrowUp" ? -1 : 1;
    const next = (idx + delta + ids.length) % ids.length;
    selectPhoneme(ids[next]);
    return;
  }

  if (event.key === "r" || event.key === "R") {
    if (!micStream) return;
    event.preventDefault();
    toggleRecording();
    return;
  }

  if (event.key === " ") {
    if (!selectedTakeId) return;
    event.preventDefault();
    togglePlay(selectedTakeId);
    return;
  }

  if (event.key === "Enter") {
    if (!selectedTakeId) return;
    event.preventDefault();
    toggleKeeper(selectedTakeId);
    return;
  }

  if (event.key === "Backspace") {
    if (!selectedTakeId) return;
    event.preventDefault();
    showDeleteConfirm(selectedTakeId);
    return;
  }

  if (event.key === "g" || event.key === "G") {
    if (!selectedPhonemeId) return;
    event.preventDefault();
    playReference();
    return;
  }

  if (event.key === "e" || event.key === "E") {
    if (!currentBank) return;
    event.preventDefault();
    runExport();
    return;
  }
}

async function runExport() {
  if (!currentBank) return;
  const bankId = bankSelect.value;
  if (!bankId) return;
  openExportModal({ pending: true });
  try {
    const summary = await postExport(bankId, { onMissingKeeper: "skip" });
    openExportModal({ summary, bankId });
  } catch (err) {
    openExportModal({ error: err, bankId });
  }
}

function openExportModal({ pending, summary, error, bankId }) {
  exportModal.hidden = false;
  document.body.classList.add("modal-open");

  if (pending) {
    exportModalBody.innerHTML = `<p class="modal__pending">Exporting bank — running ffmpeg…</p>`;
    return;
  }

  if (summary) {
    const skippedHtml = (summary.skipped ?? []).length
      ? `<details class="modal__details">
           <summary>${summary.skipped.length} phoneme(s) skipped (no keeper)</summary>
           <ul class="modal__skipped">
             ${summary.skipped
               .map(
                 (s) =>
                   `<li><code>${escapeHtml(s.id)}</code> (${escapeHtml(s.ipa)}) — ${escapeHtml(s.reason)}</li>`,
               )
               .join("")}
           </ul>
         </details>`
      : "";
    exportModalBody.innerHTML = `
      <p class="modal__status modal__status--ok">Export complete</p>
      <dl class="modal__stats">
        <dt>Exported</dt><dd>${summary.exported_count} / ${summary.phoneme_count}</dd>
        <dt>Duration</dt><dd>${formatDuration(summary.duration_ms)}</dd>
        <dt>MP3</dt><dd>${formatBytes(summary.mp3_bytes)}</dd>
        <dt>Manifest</dt><dd>${formatBytes(summary.manifest_bytes)}</dd>
      </dl>
      <p class="modal__paths">
        <code>banks/${escapeHtml(bankId)}/dist/phonemes.mp3</code><br>
        <code>banks/${escapeHtml(bankId)}/dist/phonemes.json</code>
      </p>
      ${skippedHtml}
    `;
    return;
  }

  if (error) {
    const code = error.body?.error ?? "error";
    const message = error.body?.message ?? error.message;
    const detail = error.body?.detail ?? "";
    const skipped = error.body?.skipped ?? [];
    const skippedHtml = skipped.length
      ? `<details class="modal__details" open>
           <summary>${skipped.length} phoneme(s) without a keeper</summary>
           <ul class="modal__skipped">
             ${skipped
               .map(
                 (s) =>
                   `<li><code>${escapeHtml(s.id)}</code> (${escapeHtml(s.ipa)}) — ${escapeHtml(s.reason)}</li>`,
               )
               .join("")}
           </ul>
         </details>`
      : "";
    const detailHtml = detail
      ? `<pre class="modal__stderr">${escapeHtml(detail.slice(0, 1500))}</pre>`
      : "";
    exportModalBody.innerHTML = `
      <p class="modal__status modal__status--bad">Export failed · <code>${escapeHtml(code)}</code></p>
      <p>${escapeHtml(message)}</p>
      ${skippedHtml}
      ${detailHtml}
    `;
  }
}

function closeExportModal() {
  exportModal.hidden = true;
  document.body.classList.remove("modal-open");
}

function openPrivacyFlipModal() {
  if (!currentBank) return;
  const current = currentBank.config.privacy;
  const target = current === "private" ? "public" : "private";
  privacyModal.hidden = false;
  document.body.classList.add("modal-open");
  if (target === "public") {
    renderFlipToPublic();
  } else {
    renderFlipToPrivate();
  }
}

function renderFlipToPublic() {
  const currentAttribution = currentBank?.config?.attribution ?? "";
  privacyModalTitle.textContent = "Flip bank to public?";
  privacyModalBody.innerHTML = `
    <p class="privacy-modal__warn">
      Voice is biometric data, and <strong>CC-BY-4.0 is effectively irrevocable</strong>
      once published. For minor speakers, keep the bank private unless you have
      long-term informed consent from the guardian.
    </p>
    <p>Public banks commit <code>dist/</code> to git; the per-bank
      <code>.gitignore</code> will be emptied.</p>
    <label class="privacy-modal__label">
      Attribution string (required)
      <input
        id="privacy-modal-attribution"
        type="text"
        class="privacy-modal__input"
        value="${escapeHtml(currentAttribution)}"
        placeholder="e.g. Leo Caseiro, CC BY 4.0"
        autocomplete="off"
      />
    </label>
    <label class="privacy-modal__consent">
      <input id="privacy-modal-consent" type="checkbox" />
      I confirm informed consent from the speaker (and guardian, if a minor).
    </label>
  `;
  privacyModalActions.innerHTML = `
    <button type="button" class="modal__btn" data-action="close-privacy-modal">Cancel</button>
    <button type="button" class="modal__btn modal__btn--primary" data-action="flip-to-public" disabled>
      Flip to public
    </button>
  `;

  const consent = privacyModal.querySelector("#privacy-modal-consent");
  const attribution = privacyModal.querySelector("#privacy-modal-attribution");
  const submit = privacyModal.querySelector('[data-action="flip-to-public"]');
  const syncEnabled = () => {
    submit.disabled = !consent.checked || !attribution.value.trim();
  };
  consent.addEventListener("change", syncEnabled);
  attribution.addEventListener("input", syncEnabled);
  attribution.focus();
}

function renderFlipToPrivate() {
  privacyModalTitle.textContent = "Make bank private?";
  privacyModalBody.innerHTML = `
    <p>Future exports will not be committed to git — the per-bank
      <code>.gitignore</code> will be rewritten to <code>dist/</code>.</p>
    <p class="privacy-modal__note">Recordings already committed while the bank was
      public remain in git history; removing them from history is a manual step.</p>
  `;
  privacyModalActions.innerHTML = `
    <button type="button" class="modal__btn" data-action="close-privacy-modal">Cancel</button>
    <button type="button" class="modal__btn modal__btn--primary" data-action="flip-to-private">
      Make private
    </button>
  `;
}

function closePrivacyModal() {
  privacyModal.hidden = true;
  privacyModalBody.innerHTML = "";
  privacyModalActions.innerHTML = "";
  if (exportModal.hidden) {
    document.body.classList.remove("modal-open");
  }
}

async function handlePrivacyModalClick(event) {
  const action = event.target?.dataset?.action;
  if (action === "close-privacy-modal") {
    closePrivacyModal();
    return;
  }
  if (action === "flip-to-public") {
    const attrEl = privacyModal.querySelector("#privacy-modal-attribution");
    const attribution = attrEl?.value.trim();
    if (!attribution) return;
    await applyPrivacyFlip({
      privacy: "public",
      attribution,
      confirm_flip: true,
    });
    return;
  }
  if (action === "flip-to-private") {
    await applyPrivacyFlip({ privacy: "private", confirm_flip: true });
    return;
  }
}

function openNewBankModal() {
  populateInventorySelect();
  newBankForm.reset();
  newBankError.hidden = true;
  newBankError.textContent = "";
  newBankSubmit.disabled = false;
  newBankSubmit.textContent = "Create bank";
  newBankModal.hidden = false;
  document.body.classList.add("modal-open");
  document.getElementById("new-bank-id")?.focus();
}

function closeNewBankModal() {
  newBankModal.hidden = true;
  newBankError.hidden = true;
  newBankError.textContent = "";
  if (exportModal.hidden && privacyModal.hidden) {
    document.body.classList.remove("modal-open");
  }
  newBankButton.focus();
}

function populateInventorySelect() {
  const currentBanks = Array.from(bankSelect.options)
    .map((o) => o.value)
    .filter(Boolean);
  const options = [
    { value: "english-basic", label: "English basic (44 phonemes)" },
    ...currentBanks.map((id) => ({
      value: `copy:${id}`,
      label: `Copy inventory from ${id}`,
    })),
  ];
  newBankInventorySelect.innerHTML = options
    .map(
      (o) =>
        `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`,
    )
    .join("");
}

async function submitNewBank(event) {
  event.preventDefault();
  newBankError.hidden = true;
  newBankError.textContent = "";
  newBankSubmit.disabled = true;
  newBankSubmit.textContent = "Creating…";

  const formData = new FormData(newBankForm);
  const payload = {
    id: (formData.get("id") ?? "").toString().trim(),
    name: (formData.get("name") ?? "").toString().trim(),
    locale: (formData.get("locale") ?? "").toString().trim(),
    inventory_source: (formData.get("inventory_source") ?? "english-basic")
      .toString(),
  };
  const speaker = (formData.get("speaker") ?? "").toString().trim();
  if (speaker) payload.speaker = speaker;

  try {
    const result = await postBank(payload);
    const newId = result.bank.id;
    showToast(`Created ${newId} (private)`, "success");
    closeNewBankModal();
    localStorage.setItem("last_bank_id", newId);
    await loadBanks();
  } catch (err) {
    newBankSubmit.disabled = false;
    newBankSubmit.textContent = "Create bank";
    const code = err.body?.error;
    newBankError.hidden = false;
    newBankError.textContent = code
      ? `${code}: ${err.message}`
      : err.message || "Create failed";
  }
}

async function applyPrivacyFlip(payload) {
  if (!currentBank) return;
  const bankId = bankSelect.value;
  const submit = privacyModalActions.querySelector(
    "[data-action=flip-to-public], [data-action=flip-to-private]",
  );
  if (submit) {
    submit.disabled = true;
    submit.textContent = "Saving…";
  }
  try {
    const updated = await putConfig(bankId, payload);
    currentBank.config = updated.config;
    currentBank.gitignore = updated.gitignore;
    renderPrivacyBadge(updated.config.privacy);
    renderGitignoreBanner(updated.gitignore);
    closePrivacyModal();
    showToast(
      `Privacy set to ${updated.config.privacy} · .gitignore ${updated.gitignore.status}`,
      "success",
    );
  } catch (err) {
    if (submit) {
      submit.disabled = false;
      submit.textContent =
        payload.privacy === "public" ? "Flip to public" : "Make private";
    }
    showToast(`Flip failed: ${err.message}`, "error");
  }
}

function formatDuration(ms) {
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

async function playReference() {
  if (!selectedPhonemeId) return;
  const bankId = bankSelect.value;
  const phonemeId = selectedPhonemeId;
  const refSourceEl = document.getElementById("ref-source");
  const refSource = refSourceEl ? refSourceEl.value : "auto";
  const attributionEl = document.getElementById("reference-attribution");
  if (attributionEl) attributionEl.hidden = true;

  let payload;
  try {
    payload = await getReference(bankId, phonemeId, { source: refSource });
  } catch (err) {
    const code = err.body?.error ?? "";
    if (code === "reference_missing") {
      showToast("No reference clip (run fetch scripts or try another source)", "error");
    } else {
      showToast(`Reference failed: ${err.message}`, "error");
    }
    return;
  }

  if (selectedPhonemeId !== phonemeId) return;

  if (attributionEl && payload.source === "wikimedia" && payload.attribution) {
    attributionEl.textContent = `Reference: ${payload.attribution}`;
    attributionEl.hidden = false;
  }

  try {
    await playBuffer(payload.buffer, {
      onEnded: () => {
        if (attributionEl) attributionEl.hidden = true;
      },
    });
  } catch (err) {
    if (attributionEl) attributionEl.hidden = true;
    showToast(`Reference playback failed: ${err.message}`, "error");
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

async function grantMicAndStartMeter() {
  micGrantButton.disabled = true;
  micGrantButton.textContent = "Waiting…";
  micErrorBanner.hidden = true;
  try {
    const { stream, device } = await requestMic();
    micStream = stream;
    micGrantButton.hidden = true;
    micDeviceLabel.hidden = false;
    micDeviceLabel.textContent = device;
    sizeMeterCanvas();
    window.addEventListener("resize", sizeMeterCanvas);
    startMeter(paintMeter);
    updateRecordButton();
  } catch (err) {
    micGrantButton.disabled = false;
    micGrantButton.textContent = "Grant microphone";
    micErrorBanner.hidden = false;
    micErrorBanner.textContent = micErrorMessage(err);
  }
}

function micErrorMessage(err) {
  if (err?.name === "NotAllowedError") {
    return "Microphone permission denied. Re-enable under System Settings → Privacy & Security → Microphone, then reload.";
  }
  if (err?.name === "NotFoundError") {
    return "No microphone detected. Connect one and reload.";
  }
  return `Microphone error: ${err?.message ?? err}`;
}

function sizeMeterCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const rect = meterCanvas.getBoundingClientRect();
  if (rect.width === 0) return;
  meterCanvas.width = Math.floor(rect.width * dpr);
  meterCanvas.height = Math.floor(rect.height * dpr);
}

function toggleRecording() {
  if (!micStream || savingTake) return;
  if (isRecording()) {
    finishRecording();
  } else {
    startTake();
  }
}

function startTake() {
  if (!selectedPhonemeId) {
    showToast("Select a phoneme first", "error");
    return;
  }
  try {
    startRecording(micStream);
    activeRecordingPhonemeId = selectedPhonemeId;
    updateRecordButton();
  } catch (err) {
    showToast(`Recording failed: ${err.message}`, "error");
  }
}

async function finishRecording() {
  const phonemeId = activeRecordingPhonemeId;
  const bankId = bankSelect.value;
  activeRecordingPhonemeId = null;
  savingTake = true;
  updateRecordButton();
  let blob;
  try {
    ({ blob } = await stopRecording());
  } catch (err) {
    savingTake = false;
    updateRecordButton();
    showToast(`Recording error: ${err.message}`, "error");
    return;
  }
  updateRecordButton();
  try {
    const take = await postTake(bankId, phonemeId, blob);
    applyTakeLocally(phonemeId, take);
    showToast(
      `Saved ${take.take_id} · ${take.duration_ms} ms · peak ${formatDb(take.peak_db)}`,
      "success",
    );
  } catch (err) {
    const detail = err.body?.detail ? ` — ${err.body.detail.slice(0, 200)}` : "";
    showToast(`Save failed: ${err.message}${detail}`, "error");
  } finally {
    savingTake = false;
    updateRecordButton();
  }
}

function applyTakeLocally(phonemeId, take) {
  if (!currentBank) return;
  const phonemes = currentBank.state.phonemes ??= {};
  if (!phonemes[phonemeId]) {
    phonemes[phonemeId] = { keeper_take: null, takes: [] };
  }
  phonemes[phonemeId].takes.push({
    id: take.take_id,
    created_at: take.created_at,
    duration_ms: take.duration_ms,
    peak_db: take.peak_db,
    rms_db: take.rms_db,
    notes: "",
  });
  // Mirror the server's high-water mark so a later PUT /state does
  // not send a stale value and cause the counter to rewind.
  const takeNum = parseInt(take.take_id.slice(5), 10);
  if (Number.isInteger(takeNum)) {
    const current = phonemes[phonemeId].max_take_id ?? 0;
    if (takeNum > current) phonemes[phonemeId].max_take_id = takeNum;
  }
  currentBank.state.last_phoneme_id = phonemeId;
  renderPhonemeList(currentBank);
  selectPhoneme(phonemeId, { preferTakeId: take.take_id });
}

function handleDetailClick(event) {
  const actionEl = event.target.closest("[data-action]");
  const action = actionEl?.dataset.action;

  if (action === "play-reference") {
    // Reference button lives in the phoneme header, not in a take row.
    if (pendingDeleteTakeId) {
      hideDeleteConfirm();
      return;
    }
    playReference();
    return;
  }

  const row = event.target.closest(".takes-item");
  if (!row) return;
  const takeId = row.dataset.takeId;
  if (!takeId) return;

  // Delete-confirm modality: only its own buttons do anything; clicks
  // anywhere else just close the confirm.
  if (pendingDeleteTakeId) {
    if (action === "confirm-delete") doDelete(pendingDeleteTakeId);
    else hideDeleteConfirm();
    return;
  }

  if (action === "play") {
    togglePlay(takeId);
    return;
  }
  if (action === "keeper") {
    toggleKeeper(takeId);
    return;
  }
  if (action === "delete") {
    showDeleteConfirm(takeId);
    return;
  }
  // Row body click → select the take.
  selectTake(takeId);
}

async function togglePlay(takeId) {
  const bankId = bankSelect.value;
  const phonemeId = selectedPhonemeId;
  if (!phonemeId) return;
  if (playingTakeId === takeId) {
    stopPlayback();
    playingTakeId = null;
    refreshDetailOnly();
    return;
  }
  try {
    const buffer = await getTakeWav(bankId, phonemeId, takeId);
    // Race: if another take was selected/playback request landed first, abort.
    if (selectedPhonemeId !== phonemeId) return;
    await playBuffer(buffer, {
      onEnded: () => {
        if (playingTakeId === takeId) {
          playingTakeId = null;
          refreshDetailOnly();
        }
      },
    });
    playingTakeId = takeId;
    selectedTakeId = takeId;
    refreshDetailOnly();
  } catch (err) {
    showToast(`Playback failed: ${err.message}`, "error");
  }
}

async function toggleKeeper(takeId) {
  if (!currentBank || !selectedPhonemeId) return;
  const phonemeState = currentBank.state.phonemes?.[selectedPhonemeId];
  if (!phonemeState) return;

  const previousKeeper = phonemeState.keeper_take ?? null;
  const nextKeeper = previousKeeper === takeId ? null : takeId;

  phonemeState.keeper_take = nextKeeper;
  selectedTakeId = takeId;
  renderPhonemeList(currentBank);
  refreshDetailOnly();

  try {
    await putState(bankSelect.value, currentBank.state);
  } catch (err) {
    phonemeState.keeper_take = previousKeeper;
    renderPhonemeList(currentBank);
    refreshDetailOnly();
    showToast(`Keeper save failed: ${err.message}`, "error");
  }
}

function showDeleteConfirm(takeId) {
  pendingDeleteTakeId = takeId;
  refreshDetailOnly();
}

function hideDeleteConfirm() {
  pendingDeleteTakeId = null;
  refreshDetailOnly();
}

async function doDelete(takeId) {
  const bankId = bankSelect.value;
  const phonemeId = selectedPhonemeId;
  const phonemeState = currentBank?.state?.phonemes?.[phonemeId];
  if (!phonemeState) return;

  // Snapshot for rollback.
  const previousTakes = phonemeState.takes.slice();
  const previousKeeper = phonemeState.keeper_take ?? null;

  // Optimistic remove.
  phonemeState.takes = previousTakes.filter((t) => t.id !== takeId);
  if (phonemeState.keeper_take === takeId) phonemeState.keeper_take = null;
  pendingDeleteTakeId = null;
  if (selectedTakeId === takeId) {
    selectedTakeId = defaultTakeForPhoneme(phonemeId);
  }
  if (playingTakeId === takeId) {
    stopPlayback();
    playingTakeId = null;
  }
  renderPhonemeList(currentBank);
  refreshDetailOnly();

  try {
    await deleteTake(bankId, phonemeId, takeId);
    showToast(`Deleted ${takeId}`, "success");
    if (selectedTakeId) paintWaveformForSelectedTake();
  } catch (err) {
    phonemeState.takes = previousTakes;
    phonemeState.keeper_take = previousKeeper;
    renderPhonemeList(currentBank);
    refreshDetailOnly();
    showToast(`Delete failed: ${err.message}`, "error");
  }
}

function refreshDetailOnly() {
  if (!selectedPhonemeId || !currentBank) return;
  const phoneme = currentBank.config.phonemes.find((p) => p.id === selectedPhonemeId);
  if (phoneme) {
    renderDetail(phoneme);
    paintWaveformForSelectedTake();
  }
}

async function paintWaveformForSelectedTake() {
  if (!selectedTakeId || !selectedPhonemeId) return;
  const canvas = phonemeDetail.querySelector(".take-waveform");
  if (!canvas) return;
  sizeCanvasToDisplay(canvas);
  const bankId = bankSelect.value;
  const phonemeId = selectedPhonemeId;
  const takeId = selectedTakeId;
  let buffer;
  try {
    buffer = await getTakeWav(bankId, phonemeId, takeId);
  } catch {
    return;
  }
  // Race: selection may have moved while fetching.
  if (selectedPhonemeId !== phonemeId || selectedTakeId !== takeId) return;
  try {
    await renderWaveform(canvas, buffer);
  } catch {
    // decodeAudioData can throw on odd inputs; silent.
  }
}

function sizeCanvasToDisplay(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if (rect.width === 0) return;
  canvas.width = Math.floor(rect.width * dpr);
  canvas.height = Math.floor(rect.height * dpr);
}

function updateRecordButton() {
  if (savingTake) {
    recordButton.disabled = true;
    recordButton.textContent = "Saving…";
    recordButton.classList.remove("record-button--recording");
    return;
  }
  const recording = isRecording();
  if (!micStream) {
    recordButton.disabled = true;
  } else if (recording) {
    recordButton.disabled = false;
  } else {
    recordButton.disabled = !toolsOk;
  }
  recordButton.textContent = recording ? "Stop" : "Record";
  recordButton.classList.toggle("record-button--recording", recording);
}

function ensureToast() {
  const el = document.createElement("div");
  el.className = "toast";
  el.hidden = true;
  document.body.appendChild(el);
  return el;
}

let toastTimer = null;
function showToast(message, kind = "info") {
  toastElement.className = `toast toast--${kind}`;
  toastElement.textContent = message;
  toastElement.hidden = false;
  clearTimeout(toastTimer);
  const duration = kind === "error" ? 6000 : 3000;
  toastTimer = setTimeout(() => {
    toastElement.hidden = true;
  }, duration);
}

function paintMeter({ peakDb, rmsDb }) {
  const now = performance.now();
  const dt = meterLastTimestamp ? (now - meterLastTimestamp) / 1000 : 0;
  meterLastTimestamp = now;
  meterPeakHoldDb = Math.max(
    peakDb,
    meterPeakHoldDb - METER_DECAY_DB_PER_SEC * dt,
  );
  if (meterPeakHoldDb < METER_DB_FLOOR) meterPeakHoldDb = METER_DB_FLOOR;

  const ctx = meterCanvas.getContext("2d");
  const w = meterCanvas.width;
  const h = meterCanvas.height;
  ctx.clearRect(0, 0, w, h);

  const dbToX = (db) => ((db - METER_DB_FLOOR) / -METER_DB_FLOOR) * w;

  const rmsX = Math.max(0, dbToX(rmsDb));
  const gradient = ctx.createLinearGradient(0, 0, w, 0);
  gradient.addColorStop(0, "#3fb37f");
  gradient.addColorStop(0.75, "#d08a3a");
  gradient.addColorStop(1, "#d64f4f");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, rmsX, h);

  const peakX = dbToX(meterPeakHoldDb);
  ctx.fillStyle = "#e6e8ec";
  ctx.fillRect(Math.max(0, peakX - 1), 0, 2, h);

  if (peakDb > METER_CLIP_THRESHOLD_DB) {
    ctx.fillStyle = "#d64f4f";
    ctx.fillRect(w - Math.max(4, Math.floor(w * 0.01)), 0, Math.max(4, Math.floor(w * 0.01)), h);
  }
}

init();
