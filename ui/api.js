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

export async function getReferenceSources() {
  return fetchJson("/api/reference-sources");
}

export async function getReference(bankId, phonemeId, options = {}) {
  const source = options.source ?? "auto";
  const q = new URLSearchParams();
  if (source && source !== "auto") q.set("source", source);
  const qs = q.toString();
  const suffix = qs ? `?${qs}` : "";
  const response = await fetch(
    `/api/banks/${encodeURIComponent(bankId)}/phonemes/${encodeURIComponent(phonemeId)}/reference${suffix}`,
  );
  if (!response.ok) {
    let body = null;
    try {
      body = await response.json();
    } catch {
      // body stays null
    }
    const err = new Error(body?.message ?? `HTTP ${response.status}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  const buffer = await response.arrayBuffer();
  return {
    buffer,
    source: response.headers.get("X-Reference-Source") ?? "unknown",
    attribution: response.headers.get("X-Reference-Attribution"),
  };
}

export async function getTakeWav(bankId, phonemeId, takeId) {
  const response = await fetch(
    `/api/banks/${encodeURIComponent(bankId)}/phonemes/${encodeURIComponent(phonemeId)}/takes/${encodeURIComponent(takeId)}`,
  );
  if (!response.ok) {
    const err = new Error(`HTTP ${response.status}`);
    err.status = response.status;
    throw err;
  }
  return response.arrayBuffer();
}

export async function deleteTake(bankId, phonemeId, takeId) {
  const response = await fetch(
    `/api/banks/${encodeURIComponent(bankId)}/phonemes/${encodeURIComponent(phonemeId)}/takes/${encodeURIComponent(takeId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    let body = null;
    try {
      body = await response.json();
    } catch {
      // body stays null
    }
    const err = new Error(body?.message ?? `HTTP ${response.status}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }
}

export async function postBank(payload) {
  const response = await fetch("/api/banks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let body = null;
  try {
    body = await response.json();
  } catch {
    // body stays null
  }
  if (!response.ok) {
    const err = new Error(body?.message ?? `HTTP ${response.status}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  return body;
}

export async function putConfig(bankId, payload) {
  const response = await fetch(
    `/api/banks/${encodeURIComponent(bankId)}/config`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  let body = null;
  try {
    body = await response.json();
  } catch {
    // body stays null
  }
  if (!response.ok) {
    const err = new Error(body?.message ?? `HTTP ${response.status}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  return body;
}

export async function putState(bankId, state) {
  const response = await fetch(
    `/api/banks/${encodeURIComponent(bankId)}/state`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state),
    },
  );
  let body = null;
  try {
    body = await response.json();
  } catch {
    // body stays null
  }
  if (!response.ok) {
    const err = new Error(body?.message ?? `HTTP ${response.status}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  return body;
}

export async function postExport(bankId, options = {}) {
  const payload = {};
  if (options.onMissingKeeper) payload.on_missing_keeper = options.onMissingKeeper;
  const response = await fetch(
    `/api/banks/${encodeURIComponent(bankId)}/export`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  let body = null;
  try {
    body = await response.json();
  } catch {
    // body stays null
  }
  if (!response.ok) {
    const err = new Error(body?.message ?? `HTTP ${response.status}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  return body;
}

export async function postTrim(bankId, phonemeId, takeId, startMs, endMs) {
  const response = await fetch(
    `/api/banks/${encodeURIComponent(bankId)}/phonemes/${encodeURIComponent(phonemeId)}/takes/${encodeURIComponent(takeId)}/trim`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_ms: startMs, end_ms: endMs }),
    },
  );
  let body = null;
  try {
    body = await response.json();
  } catch {
    // body stays null
  }
  if (!response.ok) {
    const err = new Error(body?.message ?? `HTTP ${response.status}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  return body;
}

export async function postTake(bankId, phonemeId, blob) {
  const response = await fetch(
    `/api/banks/${encodeURIComponent(bankId)}/phonemes/${encodeURIComponent(phonemeId)}/takes`,
    {
      method: "POST",
      headers: { "Content-Type": blob.type || "audio/webm" },
      body: blob,
    },
  );
  let body = null;
  try {
    body = await response.json();
  } catch {
    // body stays null — server returned non-JSON (unlikely here)
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
