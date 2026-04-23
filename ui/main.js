// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

import { getBank, getBanks, getHealth } from "/ui/api.js";

const banner = document.getElementById("health-banner");
const recordButton = document.getElementById("record");
const bankSelect = document.getElementById("bank-select");
const privacyBadge = document.getElementById("privacy-badge");
const phonemeList = document.getElementById("phoneme-list");
const phonemeDetail = document.getElementById("phoneme-detail");

let currentBank = null;
let selectedPhonemeId = null;

async function init() {
  renderHealth(await safeGetHealth());
  await loadBanks();
  window.addEventListener("keydown", handleKeyDown);
  bankSelect.addEventListener("change", () => loadBank(bankSelect.value));
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
    recordButton.disabled = true;
    return;
  }

  const missing = [];
  if (!body.tools?.ffmpeg) missing.push("ffmpeg");
  if (!body.tools?.espeak_ng) missing.push("espeak-ng");

  if (missing.length === 0) {
    banner.classList.add("health-banner--ready");
    banner.textContent = `Ready · v${body.version}`;
    recordButton.disabled = false;
  } else {
    banner.classList.add("health-banner--missing");
    banner.textContent = `Missing: ${missing.join(", ")} — brew install ${missing.join(" ")}`;
    recordButton.disabled = true;
  }
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

init();
