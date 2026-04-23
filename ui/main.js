// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

import { getBank, getBanks, getHealth } from "/ui/api.js";
import { requestMic, startMeter } from "/ui/audio.js";

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

const METER_DB_FLOOR = -60;
const METER_DECAY_DB_PER_SEC = 40;
const METER_CLIP_THRESHOLD_DB = -1;

let currentBank = null;
let selectedPhonemeId = null;
let meterPeakHoldDb = METER_DB_FLOOR;
let meterLastTimestamp = null;

async function init() {
  renderHealth(await safeGetHealth());
  await loadBanks();
  window.addEventListener("keydown", handleKeyDown);
  bankSelect.addEventListener("change", () => loadBank(bankSelect.value));
  micGrantButton.addEventListener("click", grantMicAndStartMeter);
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
    return;
  }

  const missing = [];
  if (!body.tools?.ffmpeg) missing.push("ffmpeg");
  if (!body.tools?.espeak_ng) missing.push("espeak-ng");

  if (missing.length === 0) {
    banner.classList.add("health-banner--ready");
    banner.textContent = `Ready · v${body.version}`;
  } else {
    banner.classList.add("health-banner--missing");
    banner.textContent = `Missing: ${missing.join(", ")} — brew install ${missing.join(" ")}`;
  }
  // Record button stays disabled until both mic is granted (M3)
  // and the recording wiring lands (M4).
  recordButton.disabled = true;
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

function selectPhoneme(id) {
  selectedPhonemeId = id;
  for (const item of phonemeList.querySelectorAll(".phoneme-item")) {
    item.classList.toggle(
      "phoneme-item--selected",
      item.dataset.phonemeId === id,
    );
  }
  if (!id || !currentBank) {
    renderEmpty("Select a phoneme to begin.");
    return;
  }
  const phoneme = currentBank.config.phonemes.find((p) => p.id === id);
  if (phoneme) renderDetail(phoneme);
}

function renderDetail(phoneme) {
  phonemeDetail.innerHTML = `
    <div class="phoneme-detail__header">
      <span class="phoneme-detail__ipa">${escapeHtml(phoneme.ipa)}</span>
      <span class="phoneme-detail__example">${escapeHtml(phoneme.example ?? "")}</span>
    </div>
    <dl class="phoneme-detail__meta">
      <dt>Id</dt><dd>${escapeHtml(phoneme.id)}</dd>
      <dt>Category</dt><dd>${escapeHtml(phoneme.category ?? "—")}</dd>
      <dt>Loopable</dt><dd>${phoneme.loopable ? "yes" : "no"}</dd>
    </dl>
    <p class="placeholder">No takes yet. Recording arrives in Milestone 4.</p>
  `;
}

function renderEmpty(message) {
  phonemeList.innerHTML = "";
  phonemeDetail.innerHTML = `<p class="placeholder">${escapeHtml(message)}</p>`;
}

function handleKeyDown(event) {
  const tag = document.activeElement?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
  if (!currentBank?.config.phonemes?.length) return;

  event.preventDefault();
  const ids = currentBank.config.phonemes.map((p) => p.id);
  const idx = Math.max(0, ids.indexOf(selectedPhonemeId));
  const delta = event.key === "ArrowUp" ? -1 : 1;
  const next = (idx + delta + ids.length) % ids.length;
  selectPhoneme(ids[next]);
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
    const { device } = await requestMic();
    micGrantButton.hidden = true;
    micDeviceLabel.hidden = false;
    micDeviceLabel.textContent = device;
    sizeMeterCanvas();
    window.addEventListener("resize", sizeMeterCanvas);
    startMeter(paintMeter);
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
