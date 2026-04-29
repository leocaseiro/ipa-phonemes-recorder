# Implementation Plan — IPA Phonemes Recorder v1

**Date:** 2026-04-23
**Spec:** [`docs/specs/2026-04-23-ipa-phonemes-recorder-design.md`](../specs/2026-04-23-ipa-phonemes-recorder-design.md)
**Status:** Ready to execute
**Owner:** Leo Caseiro

This plan translates the validated design spec into a concrete,
milestone-by-milestone build order with file-level tasks, endpoint
signatures, tests, and acceptance criteria. The app is small enough
that one plan covers v1; any section that grows unexpectedly during
implementation should be split into a dedicated sub-plan.

## Sections

1. Overview
2. Prerequisites
3. Target project structure
4. Conventions
5. Testing strategy
6. Phoneme inventory seed
7. Milestone 1 — Server skeleton + hello-world UI
8. Milestone 2 — Bank listing + phoneme list render
9. Milestone 3 — Microphone capture, meter, waveform
10. Milestone 4 — Take recording
11. Milestone 5 — Take playback, keeper selection, delete
12. Milestone 6 — Reference audio
13. Milestone 7 — Export pipeline
14. Milestone 8 — Privacy flag + per-bank `.gitignore`
15. Milestone 9 — New-bank flow + polish
16. Risks & open questions
17. Completion tracker

---

## 1. Overview

### 1.1 Goal

Deliver a localhost-only macOS tool that lets the repo owner (and
future household members / contributors) record per-phoneme IPA audio
into named **banks**, then export each bank as a BaseSkill-compatible
MP3 sprite + JSON manifest with zero changes on the BaseSkill side.

### 1.2 Constraints (from spec §3 non-goals + CLAUDE.md rules)

- No diphones, no whole-word synthesis in v1.
- No in-browser waveform editing. Trimming and loudness happen at
  export via ffmpeg.
- No cloud, no collaboration, no mobile.
- Python stdlib only. No pip, no venv, no `requirements.txt`.
- UI is plain HTML + vanilla JS. No bundler, no framework.
- Every source file begins with the MPL-2.0 header (see [LICENSE](../../LICENSE)
  Exhibit A).

### 1.3 Why small-app, single plan

Nine milestones, bounded surface (one server, one UI page, a few
ffmpeg subprocess calls), and a clear acceptance gate per milestone.
Splitting into multiple plans would add ceremony without value. The
export pipeline (Milestone 7) is the most likely candidate for
spin-off if its ffmpeg filter graph proves fiddly in practice.

---

## 2. Prerequisites

### 2.1 Host tools (must be on `PATH`)

| Tool | Minimum | Used for | Detection |
| --- | --- | --- | --- |
| `python3` | 3.10 | Server + scripts | `python3 --version` |
| `ffmpeg` | any recent | Transcode WebM→WAV, silence-trim, loudness-norm, MP3 encode | `which ffmpeg` |
| `espeak-ng` | any recent | Reference-audio fallback | `which espeak-ng` |

The server probes each at startup and exposes the result via
`GET /api/health` (see Milestone 1). The UI renders a blocking banner
if any is missing.

### 2.2 Browser

Any Chromium-based browser on macOS (Chrome, Arc, Edge) or Safari 14+.
Must support `MediaRecorder` with Opus, `AudioContext`, and
`AnalyserNode`. Tested path is Chrome; others are best-effort.

### 2.3 No package managers

Installing dependencies is explicitly out of scope. If a milestone
would need a pip package, the plan is wrong — stop and rethink.

---

## 3. Target project structure

The end-state tree after all nine milestones land:

```
ipa-phonemes-recorder/
├── LICENSE                               # already present; MPL-2.0
├── README.md                             # already present
├── CLAUDE.md                             # already present
├── .gitignore                            # already present; amended in M1
├── docs/
│   ├── specs/
│   │   └── 2026-04-23-ipa-phonemes-recorder-design.md
│   └── plans/
│       └── 2026-04-23-initial-implementation.md  # this file
├── scripts/
│   └── fetch_references.py               # M6
├── server/
│   ├── __init__.py
│   ├── app.py                            # M1: HTTP server + routing
│   ├── banks.py                          # M2: bank scan + read
│   ├── schema.py                         # M2: config validation
│   ├── takes.py                          # M4: record + metadata
│   ├── state.py                          # M2/M4: atomic state I/O
│   ├── references.py                     # M6: OGG + espeak fallback
│   ├── export.py                         # M7: ffmpeg pipeline + manifest
│   ├── gitignore.py                      # M8: per-bank gitignore sync
│   └── seeds/
│       └── english-basic.json            # M6/M9: default phoneme inventory
├── ui/
│   ├── index.html                        # M1
│   ├── main.js                           # M1→M9 (grows per milestone)
│   └── styles.css                        # M1→M9
├── banks/
│   └── en-au-leo/                        # M2: seed dev bank
│       ├── config.json
│       ├── .gitignore
│       ├── raw/                          # gitignored at root
│       ├── state.json                    # gitignored at root
│       └── dist/                         # committed iff public
├── references/                           # gitignored; populated by M6 script
├── tmp/                                  # gitignored; ffmpeg scratch
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   ├── banks/
    │   │   └── en-test/                  # 3-phoneme bank used by the export test
    │   │       ├── config.json
    │   │       ├── state.json
    │   │       └── raw/<pid>/take-001.wav
    │   └── golden/
    │       ├── phonemes.json             # byte-exact manifest for M7
    │       └── phonemes-meta.json        # expected durations + tolerances
    └── test_export.py                    # M7: the only automated test in v1
```

Milestone annotations show when each file first appears. The tree is a
target, not a dependency order — milestones may touch files that
already exist.

---

## 4. Conventions

### 4.1 Licence header

Every new `.py`, `.js`, `.html`, `.css` file starts with the MPL-2.0
notice from [LICENSE](../../LICENSE) Exhibit A, adapted to the file's
comment syntax. The tool does not generate or edit files that lack
this header.

### 4.2 Python style

- Python 3.10+, stdlib only.
- `from __future__ import annotations` at the top of every module
  that uses type hints (keeps forward refs cheap).
- Prefer `pathlib.Path` over string paths everywhere.
- Atomic writes: `write_text(tmp); os.replace(tmp, target)`. Every
  mutation of `state.json`, `config.json`, or per-bank `.gitignore`
  goes through this pattern.
- Endpoint handlers are thin: parse → delegate to module → serialise.
  Business logic lives in `server/<module>.py`, not in `app.py`.
- No globals besides constants. The server is constructed with a
  config object (`repo_root`, `port`, probed tool paths).

### 4.3 JS style

- Named exports only; no `export default` (per Leo's convention from
  BaseSkill).
- Single page; no module bundler, but use native ES modules
  (`<script type="module">`). Files imported with explicit `.js`
  extensions in the `import` path.
- No framework. Keep DOM updates explicit and local; no state-library.
- `main.js` is the entrypoint. Submodules split per-milestone
  (`api.js`, `ui-phonemes.js`, `ui-record.js`, etc.) as the file
  grows. Defer splitting until `main.js` would cross ~300 lines.

### 4.4 Endpoint shape

- All `/api/*` endpoints return `application/json` except audio byte
  streams.
- Errors return `{"error": "<code>", "message": "<human>"}` with an
  appropriate HTTP status.
- Mutations are idempotent where feasible; destructive operations
  (`DELETE`, privacy flip) require explicit request bodies, not bare
  query strings.

### 4.5 Commit and branch discipline

Per CLAUDE.md: branches named `feat/<topic>`, `fix/<topic>`,
`chore/<topic>`, `docs/<topic>`; Conventional Commits; small focused
commits. The user has explicitly approved direct-to-local-master
commits during the early docs phase of v1 — this relaxation does not
extend to code milestones, which return to the branch-per-PR flow.

---

## 5. Testing strategy

Manual QA is the primary verification path for v1. The app is small,
the user records and plays back constantly during development, and
most bugs surface immediately in use. Automated tests are reserved
for the one class of failure manual testing cannot catch.

### 5.1 The single automated test

**Export manifest shape.** BaseSkill (spec §5) does no schema
validation on `phonemes.json` — a missing key, wrong type, or extra
field means silent playback failure with no console error. Manual
listening cannot distinguish "phoneme skipped because the manifest
was malformed" from "phoneme plays at the wrong offset". A
golden-file comparison catches this for pennies.

Implementation:

- Fixture bank at `tests/fixtures/banks/en-test/` — three phonemes
  (`sh`, `k`, `ee`) covering loopable consonant, non-loopable
  consonant, and vowel. One committed keeper WAV per phoneme, each
  22.05 kHz mono under 20 kB.
- Golden outputs at `tests/fixtures/golden/`:
  - `phonemes.json` — byte-exact manifest comparison.
  - `phonemes-meta.json` — total MP3 duration + per-phoneme
    tolerance pair (`start_tolerance_ms`, `duration_tolerance_ms`),
    since MP3 frame padding shifts by a few ms across lame builds.
- Two `unittest` cases in `tests/test_export.py`:
  - `test_export_manifest_matches_golden`.
  - `test_export_mp3_properties` — sample rate 22050, channels 1,
    total duration within tolerance.

Runner: `python3 -m unittest tests.test_export`. Pre-export-milestone
there is nothing to run.

### 5.2 Manual verification per milestone

Each milestone's **Acceptance** subsection lists the manual checks
that gate completion. These replace the test suite as the pass/fail
signal. Typical checks: record, play back, inspect `state.json` on
disk, eyeball the UI layout, drop the export into BaseSkill's
`public/audio/` and verify in `WordLibraryExplorer`.

### 5.3 Bug-fix TDD still applies

Per CLAUDE.md: any bug found after a milestone is complete ships
with a failing regression test that reproduces the bug before the
fix lands. That rule is orthogonal to the "no tests for features"
relaxation — it prevents the same bug re-emerging. If a regression
test requires new modules or fixtures, that plumbing is in scope for
the fix.

### 5.4 Tools used for manual QA

- Browser DevTools for network + console during record / play.
- `afplay banks/<bank>/raw/<pid>/take-NNN.wav` to verify raw WAVs
  on disk.
- `ffprobe banks/<bank>/dist/phonemes.mp3` to spot-check exported
  sprite duration and codec.
- `python3 -m json.tool banks/<bank>/state.json` to read state.
- BaseSkill's `WordLibraryExplorer` Storybook story as the v1
  completion gate.

---

## 6. Phoneme inventory seed

### 6.1 Why a seed matters

New banks need a default phoneme list so the speaker isn't staring at
an empty UI. The seed also drives the reference-audio fetch script
and the golden export test's expected coverage.

### 6.2 Source

BaseSkill's existing sprite (`public/audio/phonemes.{mp3,json}`) is
the canonical list for English. The seed must be a **superset** of
BaseSkill's keys so any bank exported from this tool can drop in
without the consumer silently missing phonemes.

Delivered as `server/seeds/english-basic.json` — a flat array of the
same `{id, ipa, example, loopable, category}` entries used in a
bank's `config.json`. Approximately 44 entries covering General
English consonants, vowels, and the common diphthongs.

### 6.3 When it's written

Milestone 6 (reference fetch script uses it as its phoneme list) or
Milestone 9 (new-bank flow reads it), whichever lands first. The
milestone that needs it creates it; the other consumes it.

### 6.4 Copy-from-existing-bank

New-bank creation (M9) also supports copying another bank's phoneme
inventory (not its recordings) as an alternative to the English seed.
This makes it trivial to fork a bank for a second speaker with the
same inventory. Implementation is a `config.json → config.json`
phoneme-array copy with `privacy` reset to `"private"` and recordings
excluded.

---

## 7. Milestone 1 — Server skeleton + hello-world UI

**Goal:** `python3 -m server.app` starts an HTTP server on
`localhost:8766`; Chrome loads `http://localhost:8766` and shows an
empty four-zone layout with a health banner driven by
`GET /api/health`.

### 7.1 Files created

| Path | Role |
| --- | --- |
| `server/__init__.py` | Package marker (empty). |
| `server/app.py` | Entry point. Argparse (`--port`, `--repo-root`), tool probe, `ThreadingHTTPServer`, route table, static-file handler. |
| `ui/index.html` | Four-zone skeleton: top bar, left panel, centre panel, bottom meter zone. Placeholders only. |
| `ui/main.js` | ES-module entrypoint. Fetches `/api/health`, renders tool-status banner. |
| `ui/styles.css` | CSS grid for the four zones, dark palette, basic typography. |
| `.gitignore` (amend) | Add `tmp/` and `.DS_Store` if not already covered. |

### 7.2 Server shape

```python
# server/app.py
def build_server(config: ServerConfig) -> ThreadingHTTPServer: ...

@dataclass
class ServerConfig:
    repo_root: Path
    port: int
    ffmpeg: Path | None
    espeak: Path | None
```

Route table (starting set; later milestones append rows):

| Method | Path | Handler | Milestone |
| --- | --- | --- | --- |
| GET | `/` | serve `ui/index.html` | M1 |
| GET | `/ui/<path>` | serve `ui/` static files (whitelist extensions) | M1 |
| GET | `/api/health` | `{"ok": true, "tools": {"ffmpeg": bool, "espeak_ng": bool}, "version": "0.1.0"}` | M1 |

Static file handling restricts to `.html`, `.js`, `.css`, `.map`. No
traversal: reject any path containing `..`.

### 7.3 UI shape

Four-zone CSS grid layout (per spec §10.1), placeholders only:

- **Top bar**: title "IPA Phonemes Recorder" and a `<div id="health-banner">` that shows green "Ready" or red "ffmpeg missing / espeak-ng missing".
- **Left panel**: empty `<ul id="phoneme-list">`.
- **Centre panel**: empty `<section id="phoneme-detail">`.
- **Bottom zone**: empty `<div id="meter">` and `<button id="record">` (disabled).

`main.js` at M1 does one thing: fetch `/api/health`, flip the banner
class, disable the record button if any tool missing.

### 7.4 Acceptance

- `python3 -m server.app --port 8766` starts without error.
- `curl http://localhost:8766/api/health` returns expected JSON.
- Chrome loads `http://localhost:8766/`; four zones visible; health
  banner reflects reality (try `PATH=/ python3 -m server.app` to
  force missing tools).
- Spot-check: `curl -i http://localhost:8766/ui/../../etc/passwd`
  returns 4xx, not 200.

---

## 8. Milestone 2 — Bank listing + phoneme list render

**Goal:** With a seed bank present on disk, the UI shows the bank in
the top-bar dropdown, renders its phoneme list in the left panel, and
displays the privacy badge correctly. Selecting a phoneme shows its
IPA glyph and example word in the centre panel. No recording yet.

### 8.1 Files created

| Path | Role |
| --- | --- |
| `server/schema.py` | `validate_config(config: dict) -> list[str]` returns list of errors (empty on success). `REQUIRED_FIELDS`, `PRIVACY_VALUES`, `PHONEME_FIELDS` as module constants. |
| `server/banks.py` | `list_banks(repo_root) -> list[BankSummary]`; `read_bank(repo_root, bank_id) -> BankDetail`; raises `BankNotFound`, `BankInvalid`. |
| `server/state.py` | `read_state(bank_path) -> dict` (empty dict if missing or corrupt — corrupt file gets renamed to `state.json.corrupt-<ts>` per spec §14); `write_state(bank_path, state)` via temp-plus-rename. |
| `banks/en-au-leo/config.json` | Seed dev bank; `privacy: "private"`, ~10-phoneme subset for local dev. |
| `banks/en-au-leo/.gitignore` | `dist/` (private bank). |
| `banks/en-au-leo/raw/.gitkeep` | So the directory survives the gitignore. |

### 8.2 Endpoints added

| Method | Path | Response |
| --- | --- | --- |
| GET | `/api/banks` | `{"banks": [{"id", "name", "locale", "privacy", "phoneme_count"}, ...]}` |
| GET | `/api/banks/:id` | `{"config": {...}, "state": {...}}` — or `404` if bank missing, `422` if config invalid with the validator errors list |

### 8.3 Schema rules (in `server/schema.py`)

- Required: `name`, `locale`, `privacy`, `phonemes` (non-empty array).
- `privacy ∈ {"public", "private"}`.
- If `privacy == "public"`: `attribution` is required and non-empty.
- Each phoneme: `id` (ASCII slug, `[a-z0-9_]+`), `ipa` (non-empty
  string), `example` (string), `loopable` (boolean).
- `target_lufs`: optional float, defaults to `-16`.
- Duplicate `id` or duplicate `ipa` across the phonemes array →
  error.

### 8.4 UI additions

- `ui/api.js` — thin fetch wrapper: `getBanks()`, `getBank(id)`.
- `main.js` at startup: fetch bank list, populate `<select id="bank-select">`, pick the first (or last-selected via `localStorage`).
- On bank change: fetch bank, render `<ul id="phoneme-list">` with each entry showing the IPA symbol, example word, and a placeholder `○` status glyph.
- Clicking a phoneme (or `↑/↓`) updates `<section id="phoneme-detail">` with IPA glyph (large), example word, and a placeholder "No takes yet".
- Privacy badge in the top bar: green "Public" or red "Private" with a lock icon.

### 8.5 Acceptance

- `/api/banks` returns `en-au-leo`.
- `/api/banks/en-au-leo` returns the seed config + empty state.
- UI shows the bank, the phoneme list, the IPA detail, and the red
  "Private" badge.
- Hand-edit `banks/en-au-leo/config.json` to set `privacy: "bogus"`,
  reload → `/api/banks/en-au-leo` returns 422 with validator errors.
  Revert the edit.

---

## 9. Milestone 3 — Microphone capture, meter, waveform

**Goal:** Granting mic permission activates a live VU meter in the
bottom zone that moves with speech. Selecting a phoneme whose bank
has takes (fixture-injected for this milestone's manual check) renders
the take's waveform in the centre panel. No upload, no recording
persistence yet.

### 9.1 Scope

Browser-only milestone. Zero server changes. All code in `ui/`.

### 9.2 Files created / modified

| Path | Change |
| --- | --- |
| `ui/audio.js` | Audio graph owner. Exports: `requestMic()`, `startMeter(onLevel)`, `stopMeter()`, `renderWaveform(canvas, arrayBuffer)`. Named exports only. |
| `ui/main.js` | Wire mic grant UI, meter updates (rAF loop), placeholder waveform when a take WAV is hand-dropped into the fixture. |
| `ui/styles.css` | Meter styles (vertical bar, peak hold), waveform canvas styles. |
| `ui/index.html` | Add `<canvas id="meter-canvas">` and `<canvas id="waveform">`. |

### 9.3 Audio graph

```
MediaStream (mic)
  → MediaStreamSource
  → AnalyserNode (fftSize=2048, smoothingTimeConstant=0.3)
    → rAF loop reads time-domain data, computes peak + RMS, paints meter
```

Meter rendering runs at animation-frame rate; paint a simple vertical
bar + a peak-hold tick that decays over ~1.5 s. Clipping (> -1 dBFS)
paints a red cap.

### 9.4 Waveform rendering

Given an `ArrayBuffer` (WAV from the server, later milestones), decode
via `AudioContext.decodeAudioData`, downsample the channel to
canvas-width bins (min/max per bin), paint as a filled mini-waveform.
No scrubbing / no playhead marker in v1 — just a static render.

### 9.5 Mic permission UX

- On first load, do **not** auto-prompt. The user clicks a "Grant mic"
  button (appears in the bottom zone); this triggers
  `navigator.mediaDevices.getUserMedia({ audio: true })`.
- On deny: show the banner from spec §14 with macOS-specific copy
  ("Re-enable under System Settings → Privacy & Security → Microphone").
- On grant: meter starts immediately; button swaps to a device-name
  label.

### 9.6 Tests

None automated (browser-only). Manual checks listed below.

### 9.7 Acceptance (manual)

- Click "Grant mic" → browser permission prompt → granted → meter
  responds to room noise and speech.
- Meter shows peak-hold tick and red clip cap when overdriven.
- Drop a test WAV into `banks/en-au-leo/raw/sh/take-001.wav` by hand,
  update `state.json` by hand to reference it, reload UI, select
  `sh` → waveform renders. (This is a dev-loop test; Milestone 5
  replaces it with a proper endpoint + UI list.)
- Deny mic permission → banner with re-enable instructions appears,
  record button stays disabled.

---

## 10. Milestone 4 — Take recording

**Goal:** Pressing Record (button or `R`) captures mic audio, uploads
it on stop, the server transcodes to WAV, computes metadata, updates
`state.json`, and the UI shows the new take in the list. End-to-end
happy path from mic → disk.

### 10.1 Files created / modified

| Path | Change |
| --- | --- |
| `server/takes.py` | `save_take(bank_path, phoneme_id, src_bytes, src_ext) -> TakeMeta`. Writes WebM to `tmp/`, transcodes to `raw/<pid>/take-NNN.wav` at 48 kHz mono, computes metadata, updates `state.json`, cleans tmp. |
| `server/audio_meta.py` | Pure stdlib `wave` + `math`: `compute_peak_rms(path: Path) -> tuple[float, float, int]` returning `(peak_db, rms_db, duration_ms)`. Handles 16-bit PCM only in v1 (we control the encode, so this is safe). |
| `server/app.py` | Add `POST /api/banks/:id/phonemes/:pid/takes` handler. |
| `ui/record.js` | MediaRecorder wrapper: `startRecording()`, `stopRecording() -> Blob`, `onError`. Supports Opus-in-WebM. |
| `ui/main.js` | Wire record button + `R` key, POST blob on stop, refresh detail pane. |
| `ui/styles.css` | Recording state: pulsing red circle on the button, disabled state for non-record controls while active. |

### 10.2 Endpoint

```
POST /api/banks/:id/phonemes/:pid/takes
Content-Type: audio/webm   (or audio/wav if the browser produces it)
Body: raw audio bytes

201 Created
{
  "take_id": "take-003",
  "duration_ms": 642,
  "peak_db": -2.3,
  "rms_db": -18.1,
  "created_at": "2026-04-23T10:14:00Z"
}
```

Errors:

- `404` if bank or phoneme not found.
- `413` if body > 50 MB (sanity cap; a take is seconds long).
- `415` if `Content-Type` is not `audio/webm`, `audio/ogg`, or
  `audio/wav`.
- `500` with the `error.code = "ffmpeg_failed"` if transcode fails;
  the temp file stays for debugging and is logged.

### 10.3 Take numbering rule

From spec §6.3: IDs are monotonic and **never reused**. Implementation:

1. Read `state.json.phonemes[pid].takes`, collect existing IDs.
2. Also scan `raw/<pid>/` for any orphaned WAVs.
3. Parse each `take-NNN` → int; next ID = `max(existing) + 1`,
   zero-padded to 3 digits. If no existing IDs, start at `001`.
4. Deletes never decrement this counter — if 002 is deleted, the next
   recording is 003, even if only 001 remains on disk.

### 10.4 ffmpeg invocation

```
ffmpeg -y -i <tmp.webm> \
  -ar 48000 -ac 1 -c:a pcm_s16le \
  <raw/<pid>/take-NNN.wav>
```

48 kHz capture preserves headroom for the export resample to
22.05 kHz (spec §12 step 3). 16-bit PCM mono keeps files small
(~100 kB per take) and makes `audio_meta` trivial.

### 10.5 State update

On successful transcode, atomically update `state.json`:

```python
state["phonemes"].setdefault(phoneme_id, {
    "keeper_take": None,
    "takes": [],
})
state["phonemes"][phoneme_id]["takes"].append({
    "id": take_id,
    "created_at": iso_now(),
    "duration_ms": duration_ms,
    "peak_db": peak_db,
    "rms_db": rms_db,
    "notes": "",
})
state["last_phoneme_id"] = phoneme_id
write_state(bank_path, state)
```

### 10.6 UI flow

- `R` or click on record button → `startRecording()` → button enters
  red-pulse state, shows elapsed seconds.
- `R` again or click → `stopRecording()` → get Blob → POST via
  `api.js`.
- On 201: append the new take to the in-memory takes list, select
  it, render waveform.
- On error: toast with `error.message`; do not mutate UI state.

### 10.7 Acceptance

- Record a 1-second "shhh" in the UI, stop, observe:
  - `raw/sh/take-001.wav` appears, ~96 kB, playable in `afplay`.
  - `state.json` gains the take entry with plausible metadata
    (duration a few hundred ms, peak/rms in dBFS).
  - UI shows the take row with duration, peak, rms.
- Record a second take, delete `take-001` by hand from
  `state.json`, record a third — it must be `take-003`, not
  `take-002`.
- Force a ffmpeg failure (rename the binary temporarily) → POST
  returns 500 with `error.code = "ffmpeg_failed"`; `state.json` is
  unchanged.

---

## 11. Milestone 5 — Take playback, keeper selection, delete

**Goal:** The takes list in the centre panel is fully interactive.
The user can play any take (`Space`), choose the keeper (`Enter`),
and delete takes (`Backspace` with one-step confirm). All changes
survive a reload.

### 11.1 Files modified

| Path | Change |
| --- | --- |
| `server/app.py` | Add GET / DELETE handlers for individual takes, PUT handler for state. |
| `server/state.py` | `update_keeper(state, pid, take_id)` — sets `keeper_take`, clears on any other take. Validates `take_id` exists in `takes`. |
| `server/takes.py` | `delete_take(bank_path, pid, take_id)` — remove WAV, remove state entry, clear keeper if it was this take. Does not renumber siblings. |
| `ui/takes.js` | New module. Renders takes list, wires per-row play / keeper radio / delete buttons. |
| `ui/main.js` | Keyboard shortcuts: `Space`, `Enter`, `Backspace`. |
| `ui/styles.css` | Takes list layout, keeper radio styling, confirm-dialog overlay. |

### 11.2 Endpoints

| Method | Path | Response |
| --- | --- | --- |
| GET | `/api/banks/:id/phonemes/:pid/takes/:tid` | WAV bytes, `Content-Type: audio/wav`, `Content-Length` set. 404 if missing. |
| DELETE | `/api/banks/:id/phonemes/:pid/takes/:tid` | 204 on success. 404 if missing. |
| PUT | `/api/banks/:id/state` | Request body is the full state JSON; server validates shape, writes atomically. 200 with the stored state. 422 on invalid shape. |

The PUT-full-state approach keeps the client simple and avoids a
proliferation of micro-endpoints. The UI already has the full state
in memory; sending it back whole is cheap and the autosave is on a
per-action basis (spec §10.3).

### 11.3 Validation on PUT state

Reject if:

- Shape doesn't match the schema from spec §8.2.
- Any `keeper_take` references a missing take.
- More than one keeper in a phoneme (shouldn't happen; defensive).
- `takes` entries reference WAV files that don't exist on disk
  (warning, not rejection — disk is source of truth; state can
  lag briefly).

### 11.4 UI interactions

- Takes list row: `[▶ Play]  take-002  642 ms  peak −2.3 dB  rms −18.1 dB  ( ) Keeper  [🗑]`
- Click Play or press `Space`: fetch take, decode via
  `AudioContext.decodeAudioData`, play once. While playing, Play
  button becomes Stop.
- Click Keeper radio or press `Enter`: optimistic UI update, PUT
  state, roll back on failure. Status glyph in the left panel flips
  to `✓`.
- Click 🗑 or press `Backspace`: show inline confirm ("Delete
  take-002? [Delete] [Cancel]"). On confirm: DELETE request,
  optimistic removal, on failure re-insert row and toast.

### 11.5 Acceptance

- Record 3 takes of `sh`. Pick take-002 as keeper. Reload the page.
  Status glyph for `sh` is `✓`, take-002 is selected.
- Delete take-001. Take list shows only 002 and 003 with original
  IDs (no renumbering). Keeper unchanged.
- Delete take-002 (the keeper). Keeper clears; status glyph reverts
  to `●` (has takes, no keeper).
- Manual: kill the server mid-PUT (SIGKILL), restart, verify
  `state.json` is either the pre-PUT or post-PUT snapshot, never a
  half-written mess.

---

## 12. Milestone 6 — Reference audio

**Goal:** `G` (or the "Play reference" button) plays an authoritative
reference for the selected phoneme. If the Wikimedia OGG has been
fetched it plays that (with an attribution line); otherwise the
server synthesises via espeak-ng and streams the result. The export
pipeline is structurally isolated from `references/`.

### 12.1 Files created

| Path | Role |
| --- | --- |
| `scripts/fetch_references.py` | Standalone downloader. Reads the embedded `(pid, url, attribution, uploader)` table, downloads each OGG via `urllib.request`, writes `references/<pid>.ogg`, appends a row to `references/ATTRIBUTION.md`. Idempotent (skips present files, skips already-attributed rows). |
| `server/references.py` | `serve_reference(bank_path, phoneme, references_root) -> (bytes, content_type)`. First try `references/<pid>.ogg`; on miss, call `espeak_fallback(phoneme) -> wav_bytes`. |
| `server/seeds/english-basic.json` | The ~44-entry default phoneme inventory (referenced from M2 onward; created here at the latest). |
| `server/seeds/ipa_espeak_map.json` | Static map: `{"ʃ": "[[S]]", "θ": "[[T]]", ...}`. Used only by the espeak-ng fallback; not part of any bank's config. Adding phonemes to this map is an implementation follow-up, not a config change. |
| `ui/reference.js` | `playReference(bankId, phonemeId)` — fetch, play via AudioContext, show attribution overlay for the OGG case. |
| `ui/main.js` | Wire `G` key and "Play reference" button. |
| `references/ATTRIBUTION.md` | Created on first fetch; header + one row per downloaded file. |

### 12.2 Endpoint

```
GET /api/banks/:id/phonemes/:pid/reference

200 OK
Content-Type: audio/ogg          (or audio/wav for the espeak fallback)
X-Reference-Source: wikimedia    (or espeak)
X-Reference-Attribution: ...     (only when source=wikimedia)
Body: audio bytes
```

Errors:

- `404` if the bank or phoneme id does not exist.
- `502` if espeak-ng fallback is required but the binary is missing
  or exits non-zero (`error.code = "espeak_unavailable"` or
  `"espeak_failed"`).
- Never `500` for "no reference available" — a missing reference is
  a routine case handled by the fallback.

### 12.3 Fetch script behaviour

Embedded constant `WIKIMEDIA_REFERENCES: list[ReferenceEntry]` in
`scripts/fetch_references.py`:

```python
@dataclass(frozen=True)
class ReferenceEntry:
    phoneme_id: str       # matches config.json.phonemes[].id
    ipa: str              # sanity check vs the seed inventory
    url: str              # https://upload.wikimedia.org/... .ogg
    licence: str          # "CC BY-SA 3.0" etc.
    uploader: str         # Commons username
    commons_page: str     # https://commons.wikimedia.org/... (for ATTRIBUTION.md)
```

Runtime:

1. Verify `ffmpeg` and `espeak-ng` are reachable — warn but proceed
   if not (this script only needs `urllib`, but warning prevents
   running the recorder afterward with missing tools).
2. For each entry, if `references/<pid>.ogg` exists, skip.
3. Otherwise `urllib.request.urlopen(url)` with a 20 s timeout and
   a User-Agent string that identifies the tool and gives a repo URL
   (Wikimedia asks for this).
4. Stream to `references/<pid>.ogg.part`, then `os.replace` to final
   name on success.
5. If `ATTRIBUTION.md` doesn't mention this file yet, append a row.
6. Print a summary (`downloaded N, skipped M, failed K`). Non-zero
   exit iff any entry failed.

The initial reference list is seeded from the two Wikipedia pages
cited in the handoff:

- https://en.wikipedia.org/wiki/IPA_consonant_chart_with_audio
- https://en.wikipedia.org/wiki/IPA_vowel_chart_with_audio

Compiling the precise URL table is an implementation task within
this milestone — a one-off scrape captured as a static list in the
script. No runtime scraping.

### 12.4 espeak-ng fallback

For a phoneme without a cached OGG:

1. Look up `phoneme.ipa` in `server/seeds/ipa_espeak_map.json` to
   find the Kirshenbaum fragment (e.g., `ʃ` → `[[S]]`).
2. If the IPA is unmapped, return 502 with
   `error.code = "espeak_no_mapping"` and log.
3. Invoke:

   ```
   espeak-ng -v en -s 120 --stdout "<kirshenbaum>"
   ```

   Capture stdout as WAV bytes. 16 kHz mono is fine for a reference
   clip.
4. Stream the bytes back with `Content-Type: audio/wav` and
   `X-Reference-Source: espeak`.

No disk I/O for the fallback — the WAV lives entirely in memory.

### 12.5 Isolation guarantee

`server/export.py` (M7) **must not** open any path outside the
bank's own root. Enforcement is structural: the export module
imports no helper that accesses `references/`, and every file open
in the pipeline is reviewed against this rule during M7. No runtime
assertion in v1 — manual code review plus the fact that the pipeline
parameters (`bank_path`, `tmp_root`) never receive a references path
are the guards.

### 12.6 Acceptance

- Run `python3 scripts/fetch_references.py` → OGGs appear under
  `references/`, `ATTRIBUTION.md` lists each with its Commons
  uploader + licence.
- In the UI, select `ʃ`, press `G` → Wikimedia OGG plays; brief
  attribution line visible during playback.
- Delete `references/sh.ogg` → press `G` → espeak-ng synthesis plays;
  no attribution line shown.
- Grep check: `grep -R "references" server/export.py` returns no
  matches (cheap structural confirmation of §12.5).

---

## 13. Milestone 7 — Export pipeline

**Goal:** `E` (or "Export bank") writes `dist/phonemes.mp3` +
`dist/phonemes.json` whose manifest matches BaseSkill's expected
shape exactly and whose MP3 plays at the correct offsets when
dropped into BaseSkill's `public/audio/`.

### 13.1 Files created

| Path | Role |
| --- | --- |
| `server/export.py` | Full pipeline: read config+state, select keepers, run ffmpeg filter chain per keeper into `tmp/`, concat with silent gaps, encode MP3, build manifest with cumulative offsets, write `dist/`. |
| `server/ffmpeg_util.py` | Thin subprocess wrappers: `run(cmd, *, check=True) -> CompletedProcess`; `probe_duration_ms(path) -> int` via `ffprobe`. Also: `FFmpegError` with stderr captured. |
| `tests/__init__.py` | Empty; marks the package so `python3 -m unittest tests.test_export` works. |
| `tests/test_export.py` | The two automated cases: golden manifest comparison + MP3 property bounds. |
| `tests/fixtures/banks/en-test/config.json` | 3-phoneme fixture bank. |
| `tests/fixtures/banks/en-test/state.json` | Keeper pointers for the three fixture takes. |
| `tests/fixtures/banks/en-test/raw/sh/take-001.wav` | Keeper WAV used by the export test. |
| `tests/fixtures/banks/en-test/raw/k/take-001.wav` | Keeper WAV. |
| `tests/fixtures/banks/en-test/raw/ee/take-001.wav` | Keeper WAV. |
| `tests/fixtures/golden/phonemes.json` | Byte-exact expected manifest for the en-test fixture. |
| `tests/fixtures/golden/phonemes-meta.json` | Total duration + per-phoneme tolerance. |
| `ui/export.js` | Fire the POST, render the summary modal. |
| `ui/main.js` | Wire `E` key and "Export bank" button. |

### 13.2 Endpoint

```
POST /api/banks/:id/export
Content-Type: application/json
{
  "on_missing_keeper": "skip" | "fail"   // default "skip"
}

200 OK
{
  "phoneme_count": 44,
  "exported_count": 42,
  "skipped": [
    { "id": "zh", "ipa": "ʒ", "reason": "no keeper" }
  ],
  "duration_ms": 21640,
  "mp3_bytes": 152418,
  "manifest_bytes": 2103,
  "warnings": []
}
```

Errors:

- `400 zero_keepers` if no phoneme in the bank has a keeper take.
- `400 missing_keepers` if `on_missing_keeper == "fail"` and any
  phoneme is missing a keeper; include the list in the response.
- `409 gitignore_drift` if the bank is private but its
  `.gitignore` does not contain `dist/` (Milestone 8 auto-fixes;
  this is a defensive catch for M7-only deployments).
- `500 ffmpeg_failed` with the stderr of the first failing call in
  `error.detail`.

### 13.3 Pipeline steps (spec §12 restated with concrete calls)

**Step 1 — Collect keepers.** Iterate `config.phonemes`. For each,
look up `state.phonemes[id].keeper_take`. Absent → per
`on_missing_keeper`. Present → record
`(phoneme, raw/<pid>/<take_id>.wav)`.

**Step 2 — Per-keeper filter.** For each `(phoneme, wav_path)`:

```
ffmpeg -y -i <wav_path> \
  -af "silenceremove=stop_periods=-1:stop_duration=0.05:stop_threshold=-50dB, \
       loudnorm=I=<target_lufs>:TP=-1.5:LRA=11" \
  -ar 22050 -ac 1 \
  tmp/<bank-id>/<pid>.wav
```

`<target_lufs>` comes from `config.target_lufs` (default `-16`).

**Step 3 — Build concat list.** For each filtered WAV, interleave a
25 ms silent WAV (`ffmpeg -f lavfi -i anullsrc=r=22050:cl=mono -t 0.025`
produced once and reused). Write an ffmpeg concat demuxer file:

```
file 'sh.wav'
file 'silence.wav'
file 'k.wav'
file 'silence.wav'
...
```

**Step 4 — Compute offsets.** Do **not** rely on post-hoc ffprobe of
the concatenated output; instead probe each filtered WAV individually
(ffprobe) and compute cumulative ms offsets in Python. This gives
deterministic manifest offsets even if the MP3 encoder adds frame
padding. Silent gaps count toward the next phoneme's offset.

**Step 5 — Concat + encode to MP3.**

```
ffmpeg -y -f concat -safe 0 -i concat.txt \
  -c:a libmp3lame -q:a 6 -ar 22050 -ac 1 \
  dist/phonemes.mp3
```

**Step 6 — Emit manifest.**

```json
{
  "ʃ":  { "start": 0,    "duration": 642, "loopable": true },
  "k":  { "start": 667,  "duration": 90 },
  "iː": { "start": 782,  "duration": 701, "loopable": true }
}
```

Note: `loopable: false` is omitted from output to match BaseSkill's
manifest style (spec §5's example has `loopable` absent for `k`).

**Step 7 — Atomic write.** Write MP3 to `dist/phonemes.mp3.tmp` and
manifest to `dist/phonemes.json.tmp`; `os.replace` both onto their
final names. Either both land or neither does (implementation writes
manifest first, MP3 second; on MP3 write failure, revert the
manifest from backup). A simpler option: write both to a `dist.tmp/`
sibling directory, then `os.replace` the directory. Choose whichever
is simpler given ffmpeg's output target being a direct file.

**Step 8 — Safety gate.** If `config.privacy == "private"`, call the
M8 helper `verify_bank_gitignore(bank_path)` first. If it reports
drift, auto-fix before writing. If auto-fix fails, return 409.

**Step 9 — Cleanup.** On success, delete `tmp/<bank-id>/`. On
failure, leave tmp intact and include the tmp path in the error
response for debugging.

### 13.4 Automated tests (the only ones in v1)

Two `unittest` cases in `tests/test_export.py`:

- `test_export_manifest_matches_golden` — run the pipeline against
  `tests/fixtures/banks/en-test/`. To keep output deterministic
  across lame / ffmpeg builds, the test invokes `export_bank(...,
  deterministic=True)` which substitutes `loudnorm` for a null
  filter. Manifest must equal `tests/fixtures/golden/phonemes.json`
  byte-for-byte.
- `test_export_mp3_properties` — decode the resulting MP3 via
  `ffprobe`, assert sample rate 22050, channel count 1, and total
  duration within the tolerance in `phonemes-meta.json`.

Runner: `python3 -m unittest tests.test_export`. This is the only
automated check for v1 — everything else is manual per §5.

### 13.5 Acceptance

- Dev bank has keepers for ≥ 5 phonemes. `POST /api/banks/en-au-leo/export`
  returns 200 with a summary.
- Copy `banks/en-au-leo/dist/phonemes.mp3` and `phonemes.json` into
  `~/Sites/base-skill/public/audio/`. Open the BaseSkill
  `WordLibraryExplorer` Storybook story. Playback of every included
  phoneme works, loopable phonemes sustain, no console errors.
- `python3 -m unittest tests.test_export` passes.
- Edge cases checked manually: export with zero keepers returns 400;
  export with one missing keeper and `on_missing_keeper=skip` omits
  that phoneme from the manifest; same setup with `fail` returns
  400 and writes no files; after a forced ffmpeg failure
  `tmp/<bank-id>/` is still present for debugging.

---

## 14. Milestone 8 — Privacy flag + per-bank `.gitignore`

**Goal:** The per-bank `.gitignore` is the tool's responsibility and
matches the bank's `privacy` field at all times. Flipping a bank from
private to public requires explicit, friction-ful confirmation that
documents informed consent. The pipeline refuses to export a private
bank whose `.gitignore` is drifted.

### 14.1 Files created / modified

| Path | Change |
| --- | --- |
| `server/gitignore.py` | `expected_content(privacy) -> str`; `verify(bank_path, privacy) -> GitignoreStatus`; `sync(bank_path, privacy) -> GitignoreStatus`. Atomic write via temp-plus-rename. |
| `server/banks.py` | On read, call `verify(...)` and include a `gitignore` field in the detail response: `{"status": "ok" \| "drifted" \| "missing", "expected": str, "current": str}`. |
| `server/export.py` | At step 8, call `sync(...)` when privacy=private and the status is not "ok". Raise `GitignoreSyncFailed` (→ 409) if the sync itself fails. |
| `server/app.py` | Add `PUT /api/banks/:id/config` (limited: only `privacy` and `attribution` mutable). |
| `ui/privacy.js` | Badge click handler, confirm modal, attribution textbox. |
| `ui/main.js` | Mount privacy.js; on bank load, render drift warning if present. |
| `ui/styles.css` | Modal styling, drift-warning banner (yellow). |

### 14.2 `.gitignore` content rules

| Bank privacy | Per-bank `.gitignore` |
| --- | --- |
| `private` | Exactly `dist/\n`. No other lines. |
| `public` | File absent, or empty. |

Why so strict? The root `.gitignore` already covers `raw/` and
`state.json`. The per-bank file's only job is `dist/`, and keeping it
minimal makes drift detection an equality check, not a grammar
parse. If a user adds custom lines, the tool treats the file as
drifted and surfaces a yellow banner with both the expected and
current contents — it does not overwrite custom additions without
the user clicking "Sync".

### 14.3 Config PUT endpoint

```
PUT /api/banks/:id/config
Content-Type: application/json
{
  "privacy": "public",
  "attribution": "Leo Caseiro, CC BY 4.0",
  "confirm_flip": true              // required if privacy changes
}

200 OK
{ "config": <full updated config>, "gitignore": {"status": "ok", ...} }
```

Errors:

- `400 confirm_required` if `privacy` changes and `confirm_flip`
  isn't `true`.
- `422 attribution_required` if resulting privacy is `public` and
  attribution is empty.
- `422 invalid_privacy`.

The PUT only accepts `privacy` and `attribution`. All other config
fields (phoneme inventory, target_lufs) are edited by hand in
`config.json`. This is a deliberate limitation — wholesale config
editing in the UI is out of scope for v1.

### 14.4 UI flow

- The privacy badge in the top bar is clickable.
- Private → public flip: modal with spec §13.3 copy verbatim,
  attribution textbox (pre-filled from config if any), and a two-
  step confirm button ("I confirm informed consent from the speaker
  and, where applicable, their guardian → Flip to public"). The
  button is disabled until the textbox has non-whitespace content.
  Second click fires the PUT.
- Public → private flip: single-step confirm ("Make this bank
  private? Future exports won't be committed.") — less friction
  since we're moving toward more safety, not away.
- After a successful flip, the badge flips colour, a toast confirms
  "Privacy set to `<value>`, .gitignore synced."
- Drift banner: yellow banner with expected / current diff and a
  "Sync" button. Clicking "Sync" calls the PUT with the same privacy
  (no-op flip) to trigger a re-sync, or a dedicated endpoint if we
  add one.

### 14.5 Acceptance

- On a private bank with `dist/` in its `.gitignore`, `/api/banks/:id`
  reports `gitignore.status = "ok"` and no banner appears.
- Manually edit `banks/en-au-leo/.gitignore` to remove `dist/`,
  reload UI → yellow banner with expected vs current → click Sync →
  banner clears and `.gitignore` contains `dist/\n` again.
- Flip badge to public without typing an attribution → textbox is
  required; no request fires.
- Flip completes → badge green, tooltip shows attribution, per-bank
  `.gitignore` is now empty (not missing; empty-file is fine per
  §14.2).
- `curl -X PUT ... -d '{"privacy":"public"}'` without `confirm_flip`
  → 400 `confirm_required`.
- Run export on a private bank whose `.gitignore` is hand-deleted;
  export auto-syncs and succeeds. Delete `.gitignore` and make it
  read-only (`chmod 444`); export returns 409 `gitignore_drift` and
  no `dist/` bytes are written.

---

## 15. Milestone 9 — New-bank flow + polish

**Goal:** The user can create a new bank from the UI without editing
filesystem files by hand. Every bank starts private. The UI is
keyboard-navigable end-to-end, autosaves silently with status toasts,
and surfaces server errors without losing user state.

### 15.1 Files created / modified

| Path | Change |
| --- | --- |
| `server/app.py` | Add `POST /api/banks` endpoint. |
| `server/banks.py` | `create_bank(repo_root, payload) -> BankSummary`. Validates id uniqueness and slug shape; writes folder skeleton, config.json, empty state.json, per-bank .gitignore. |
| `ui/new-bank.js` | Modal form, inventory-source dropdown (`english-basic` / `copy:<existing-bank-id>`). |
| `ui/shortcuts.js` | Central keyboard dispatcher. Each milestone's shortcuts register here; this module owns the global listener and delegates to handlers. |
| `ui/toasts.js` | Minimal toast queue (success / error / info). |
| `ui/main.js` | Wire new-bank button, shortcut dispatcher, toast host. |
| `ui/styles.css` | Modal + toast styles. Keyboard focus rings. |

### 15.2 Endpoint

```
POST /api/banks
Content-Type: application/json
{
  "id": "en-us-sam",
  "name": "General American — Sam",
  "locale": "en-US",
  "speaker": "Sam Doe",
  "inventory_source": "english-basic" | "copy:<existing-bank-id>"
}

201 Created
{ "bank": <BankSummary>, "path": "banks/en-us-sam" }
```

Errors:

- `409 bank_id_exists` if the folder already exists.
- `422 invalid_id` if the id isn't `[a-z0-9-]+`.
- `422 invalid_locale` if locale isn't `xx` or `xx-XX` shape.
- `422 unknown_inventory_source` if the source id can't be resolved.

The new bank is always created with `privacy: "private"` and no
`attribution`. Flipping to public happens through M8's PUT endpoint.

### 15.3 UI flow

- "New bank" button in top bar opens a modal with:
  - Bank id (slug, auto-suggested from locale+speaker)
  - Display name
  - Locale (dropdown of common values + free-text fallback)
  - Speaker name
  - Inventory source: `english-basic` or any existing bank
  - A small note: "Default privacy: **private**. Voice is biometric
    data; CC-BY-4.0 is effectively irrevocable once published. For
    minor speakers, keep private unless you have long-term informed
    consent from the guardian."
- On submit: POST → on 201, bank appears in the dropdown and is
  selected automatically. Toast: "Created en-us-sam (private)."

### 15.4 Polish checklist

- **Keyboard shortcuts** — full list from spec §10.2 dispatched via
  `ui/shortcuts.js`. Each handler no-ops if the focus is inside a
  text input (so typing attribution doesn't trigger `R`).
- **Autosave toasts** — brief "Saved" flash on every successful PUT
  state; replace with red "Save failed — retry?" on error, leaving
  the UI in its pre-PUT state so the user can retry.
- **Health banner** — from M1, refined: on tool-missing it now
  includes a one-line install hint (`brew install ffmpeg espeak-ng`).
- **Last input device label** — persisted in state (spec §6.4);
  shown next to the mic-grant button after the first grant.
- **Optimistic UI with rollback** — every mutation updates the UI
  immediately, fires the PUT, and rolls back on failure. This
  applies to keeper change, delete, notes edit.
- **Error surface** — any unexpected 5xx from the server shows a
  modal with the `error.message` and a "Copy details" button (to
  make issue reporting easier).
- **No auto-focus traps** — every modal closes on `Esc` and focuses
  the element that opened it on close.

### 15.5 Acceptance

- Create a new bank `en-us-sam` using the English-basic inventory →
  folder appears with config, empty state, private `.gitignore`.
  Bank is selected in the UI with the full phoneme list and red
  "Private" badge.
- Create a second bank that copies `en-au-leo`'s inventory → new
  bank's phoneme array matches the source, but no recordings are
  copied.
- Attempt to create a bank with a duplicate id → 409; with an
  uppercase or space-containing id → 422.
- Every spec §10.2 shortcut works when the phoneme list or takes
  list has focus, and is correctly suppressed when a text field has
  focus.
- Stop the server mid-autosave (Ctrl-C during a keeper flip) → red
  "Save failed — retry?" toast; UI state unchanged; restart server
  and retry works.
- `python3 -m unittest tests.test_export` still passes after M9's
  changes.
- Manual end-to-end pass: record a 5-phoneme bank, export, drop into
  BaseSkill, verify in `WordLibraryExplorer`. **This is the v1
  completion gate.**

---

## 16. Risks & open questions

### 16.1 Known risks

- **ffmpeg `loudnorm` nondeterminism.** `loudnorm` uses a two-pass
  algorithm whose output can drift by a few samples between versions
  or even between runs. Mitigation: the export test disables
  `loudnorm` via a test-only config path and compares the manifest
  byte-for-byte; MP3 duration checks use tolerances.
- **MediaRecorder codec portability.** Chrome produces WebM/Opus by
  default; Safari may produce MP4/AAC. The server's ffmpeg call
  accepts both (`-i` auto-detects) but we should log the actual
  `Content-Type` received and verify on both browsers during M4
  acceptance.
- **Subprocess output size.** Ffmpeg stderr for a single take is
  small, but a full export pipes many stderrs through. Capture via
  `subprocess.run(..., capture_output=True)` with a size cap; if
  exceeded, log to disk and truncate the in-memory copy.
- **State.json growth.** After hundreds of takes, `state.json` can
  become a few hundred kB. Not a v1 concern, but avoid any operation
  that re-serialises state on every keystroke (notes field should
  PUT on blur, not on each character).
- **Race between two browser tabs.** Spec §14 says "last write
  wins". Ensure PUT state is atomic (already guaranteed by
  temp-plus-rename) so a race produces one valid state, never a
  merged mutant.

### 16.2 Open questions (resolve during implementation)

- **IPA → Kirshenbaum map completeness.** The static map at
  `server/seeds/ipa_espeak_map.json` needs coverage for the full
  english-basic seed. Populating it is a per-phoneme lookup
  exercise; if a phoneme has no plausible espeak rendering, the
  fallback returns 502 and the UI shows a friendly "no reference
  available" message. Track gaps by running the seed against the
  fallback and logging all `espeak_no_mapping` responses.
- **Port-in-use behaviour.** Detect `EADDRINUSE` on startup and
  either (a) fail with a clear message pointing to `--port`, or
  (b) probe 8766…8775. Prefer (a) for predictability.
- **Wikimedia URL drift.** Commons occasionally moves or re-licenses
  files. The fetch script logs 404s; re-running periodically with
  updates to the constant table is manual housekeeping.
- **Dist directory atomicity.** §13.3 step 7 proposes two options
  (tmp-pair-replace vs tmp-directory-replace). Pick during M7
  implementation — the simpler one wins.
- **Storybook story name for v1 gate.** Confirm the exact story is
  still `WordLibraryExplorer` in BaseSkill; the current
  implementation in `~/Sites/base-skill` is the source of truth.

### 16.3 Things deferred out of scope (spec §17 restated)

- Diphones / whole-word synthesis.
- Short / long variant tracks per phoneme.
- In-browser waveform editing.
- Multi-bank UI swap in BaseSkill (requires consumer-side change).
- Import / export banks as zip files.
- Automated pre-push symlink into BaseSkill.

---

## 17. Completion tracker

Tick each milestone only when its acceptance criteria are met and its
tests are green.

- [ ] **M1** — Server skeleton + hello-world UI (`/api/health`, four-zone layout)
- [ ] **M2** — Bank listing + phoneme list render (seed `en-au-leo`, schema validation)
- [ ] **M3** — Mic capture, meter, waveform (manual QA only)
- [ ] **M4** — Take recording end-to-end (POST → ffmpeg → state)
- [ ] **M5** — Take playback, keeper selection, delete (full autosave)
- [ ] **M6** — Reference audio (fetch script + espeak fallback + isolation test)
- [ ] **M7** — Export pipeline (golden-file manifest test + BaseSkill drop-in verified)
- [ ] **M8** — Privacy flag + per-bank `.gitignore` (drift detection + sync + PUT config)
- [ ] **M9** — New-bank flow + polish (shortcuts, toasts, end-to-end gate)

**v1 completion gate:** a recorded bank exported from this tool plays
correctly in BaseSkill's `WordLibraryExplorer` with no console
errors, every spec §10.2 shortcut works, and every private bank's
per-bank `.gitignore` passes drift verification.
