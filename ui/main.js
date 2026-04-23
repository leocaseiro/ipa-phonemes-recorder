// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

const banner = document.getElementById("health-banner");
const recordButton = document.getElementById("record");

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json();
    renderHealth(body);
  } catch (err) {
    renderHealthError(err);
  }
}

function renderHealth(body) {
  const missing = [];
  if (!body.tools?.ffmpeg) missing.push("ffmpeg");
  if (!body.tools?.espeak_ng) missing.push("espeak-ng");

  banner.classList.remove(
    "health-banner--unknown",
    "health-banner--ready",
    "health-banner--missing",
  );

  if (missing.length === 0) {
    banner.classList.add("health-banner--ready");
    banner.textContent = `Ready · v${body.version}`;
    recordButton.disabled = false;
  } else {
    banner.classList.add("health-banner--missing");
    banner.textContent = `Missing: ${missing.join(", ")} — install via brew install ${missing.join(" ")}`;
    recordButton.disabled = true;
  }
}

function renderHealthError(err) {
  banner.classList.remove(
    "health-banner--unknown",
    "health-banner--ready",
    "health-banner--missing",
  );
  banner.classList.add("health-banner--missing");
  banner.textContent = `Health check failed: ${err.message}`;
  recordButton.disabled = true;
}

checkHealth();
