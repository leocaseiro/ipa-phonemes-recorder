// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// MediaRecorder wrapper. Picks the best-supported MIME type (Opus in
// WebM preferred), accumulates blob chunks, and returns one composite
// blob on stop. State lives in module scope; only one active recorder
// at a time.

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
  "audio/mp4",
];

let recorder = null;
let chunks = [];
let pickedMimeType = "";

function pickMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  for (const candidate of MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(candidate)) return candidate;
  }
  return "";
}

export function isRecording() {
  return recorder !== null && recorder.state === "recording";
}

export function startRecording(stream) {
  if (isRecording()) throw new Error("already recording");
  chunks = [];
  pickedMimeType = pickMimeType();
  const options = pickedMimeType ? { mimeType: pickedMimeType } : {};
  recorder = new MediaRecorder(stream, options);
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  recorder.start(100);
}

export function stopRecording() {
  return new Promise((resolve, reject) => {
    if (!recorder || recorder.state === "inactive") {
      reject(new Error("no active recorder"));
      return;
    }
    const pending = recorder;
    pending.onstop = () => {
      const mime = pendingMime(pending);
      const blob = new Blob(chunks, { type: mime });
      recorder = null;
      chunks = [];
      pickedMimeType = "";
      resolve({ blob, mimeType: mime });
    };
    pending.onerror = (event) => {
      recorder = null;
      chunks = [];
      pickedMimeType = "";
      reject(event.error ?? new Error("recorder error"));
    };
    pending.stop();
  });
}

function pendingMime(rec) {
  return pickedMimeType || rec.mimeType || "audio/webm";
}
