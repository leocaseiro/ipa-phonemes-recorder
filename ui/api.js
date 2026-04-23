// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

async function fetchJson(url) {
  const response = await fetch(url);
  let body = null;
  try {
    body = await response.json();
  } catch {
    // fall through — body stays null
  }
  if (!response.ok) {
    const message = body?.message ?? `HTTP ${response.status}`;
    const err = new Error(message);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  return body;
}

export async function getHealth() {
  return fetchJson("/api/health");
}

export async function getBanks() {
  return fetchJson("/api/banks");
}

export async function getBank(id) {
  return fetchJson(`/api/banks/${encodeURIComponent(id)}`);
}
