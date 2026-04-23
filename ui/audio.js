// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Audio graph owner. Holds the shared AudioContext, the mic stream,
// and the Analyser for metering. Also decodes committed WAVs into
// waveform renders. No recording logic — that lands in M4.

const DB_FLOOR = -60;

let audioContext = null;
let micStream = null;
let meterState = null;
let playbackSource = null;

function ensureContext() {
  if (!audioContext) {
    const Ctx = window.AudioContext ?? window.webkitAudioContext;
    audioContext = new Ctx();
  }
  return audioContext;
}

function deviceLabel(stream) {
  const track = stream.getAudioTracks()[0];
  return track?.label?.trim() || "Default microphone";
}

function toDb(linear) {
  if (!Number.isFinite(linear) || linear <= 0) return DB_FLOOR;
  const db = 20 * Math.log10(linear);
  return db < DB_FLOOR ? DB_FLOOR : db;
}

export async function requestMic() {
  if (micStream) return { stream: micStream, device: deviceLabel(micStream) };
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const ctx = ensureContext();
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      // non-fatal; iOS/Safari sometimes needs a gesture
    }
  }
  micStream = stream;
  return { stream, device: deviceLabel(stream) };
}

export function startMeter(onLevel) {
  if (!micStream) throw new Error("startMeter called before requestMic");
  if (meterState) stopMeter();

  const ctx = ensureContext();
  const source = ctx.createMediaStreamSource(micStream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.3;
  source.connect(analyser);

  const buffer = new Float32Array(analyser.fftSize);
  const state = { rafId: 0, analyser, source };
  meterState = state;

  function tick() {
    analyser.getFloatTimeDomainData(buffer);
    let peak = 0;
    let sumSquares = 0;
    for (let i = 0; i < buffer.length; i++) {
      const sample = buffer[i];
      const abs = Math.abs(sample);
      if (abs > peak) peak = abs;
      sumSquares += sample * sample;
    }
    const rms = Math.sqrt(sumSquares / buffer.length);
    onLevel({ peakDb: toDb(peak), rmsDb: toDb(rms) });
    state.rafId = requestAnimationFrame(tick);
  }

  state.rafId = requestAnimationFrame(tick);
}

export function stopMeter() {
  if (!meterState) return;
  cancelAnimationFrame(meterState.rafId);
  try {
    meterState.source.disconnect();
  } catch {
    // ignore — already disconnected
  }
  meterState = null;
}

export async function renderWaveform(canvas, arrayBuffer) {
  const ctx = ensureContext();
  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));
  const data = audioBuffer.getChannelData(0);
  paintWaveform(canvas, data);
}

export async function playBuffer(arrayBuffer, { onEnded } = {}) {
  const ctx = ensureContext();
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      // non-fatal
    }
  }
  stopPlayback();
  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));
  const source = ctx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(ctx.destination);
  source.onended = () => {
    if (playbackSource === source) {
      playbackSource = null;
      onEnded?.();
    }
  };
  playbackSource = source;
  source.start();
  return source;
}

export function stopPlayback() {
  if (!playbackSource) return;
  try {
    playbackSource.stop();
  } catch {
    // already stopped
  }
  playbackSource = null;
}

export function isPlaying() {
  return playbackSource !== null;
}

function paintWaveform(canvas, data) {
  const ctx2d = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const mid = height / 2;
  const binSize = Math.max(1, Math.floor(data.length / width));
  const stroke =
    getComputedStyle(canvas).getPropertyValue("--waveform").trim() || "#6aa9ff";

  ctx2d.clearRect(0, 0, width, height);
  ctx2d.fillStyle = stroke;

  for (let x = 0; x < width; x++) {
    let min = 1;
    let max = -1;
    const start = x * binSize;
    const end = Math.min(start + binSize, data.length);
    for (let i = start; i < end; i++) {
      const sample = data[i];
      if (sample < min) min = sample;
      if (sample > max) max = sample;
    }
    if (min === 1 && max === -1) {
      min = 0;
      max = 0;
    }
    const yTop = mid - max * mid;
    const yBottom = mid - min * mid;
    ctx2d.fillRect(x, yTop, 1, Math.max(1, yBottom - yTop));
  }
}

export const DB_FLOOR_CONST = DB_FLOOR;
