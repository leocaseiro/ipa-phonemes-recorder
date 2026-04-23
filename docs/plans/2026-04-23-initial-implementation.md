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
|---|---|---|---|
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
    │   │   └── en-test/                  # tiny bank used across tests
    │   │       ├── config.json
    │   │       ├── state.json
    │   │       └── raw/<pid>/take-001.wav
    │   └── golden/
    │       ├── phonemes.json             # golden manifest for M7
    │       └── phonemes-meta.json        # expected durations / bounds
    ├── test_app.py                       # M1
    ├── test_banks.py                     # M2
    ├── test_schema.py                    # M2
    ├── test_takes.py                     # M4
    ├── test_state.py                     # M4
    ├── test_references.py                # M6
    ├── test_export.py                    # M7
    └── test_gitignore.py                 # M8
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

### 5.1 What we test

| Layer | Tool | Scope |
|---|---|---|
| Python modules | `unittest` (stdlib) | Schema validation, state I/O, take metadata math, export pipeline, gitignore sync |
| HTTP endpoints | `unittest` against in-process `http.server` | Route wiring, status codes, request/response shapes |
| ffmpeg pipeline | Golden-file comparison on manifest; tolerance-based compare on MP3 | Manifest JSON exact-match; MP3 duration and sample-rate within bounds |
| UI | Manual only | Four-zone layout, keyboard shortcuts, record/play cycle, privacy confirmations |
| End-to-end | Manual | Export bank, drop into `base-skill/public/audio/`, verify in `WordLibraryExplorer` story |

### 5.2 Test runner

`python3 -m unittest discover tests` from the repo root. Exit code is
the CI signal (if CI is added later). No external runner, no
coverage tool in v1.

### 5.3 Fixtures

A single fixture bank lives at `tests/fixtures/banks/en-test/` with
three phonemes (`sh`, `k`, `ee`) chosen to exercise loopable vs
non-loopable vs vowel. Each has one keeper WAV committed (22.05 kHz
mono, under 20 kB each) so export tests are fully offline.

Golden outputs for the export test live at `tests/fixtures/golden/`:

- `phonemes.json` — byte-exact manifest comparison.
- `phonemes-meta.json` — expected total duration in ms and a
  per-phoneme `{start_tolerance_ms, duration_tolerance_ms}` pair.
  Tolerances exist because MP3 frame boundaries shift by a few ms
  across lame versions.

### 5.4 TDD policy

Per CLAUDE.md:

- **Bug fixes:** failing test first, confirm repro, then fix.
- **Features:** tests alongside the implementation, not after. For
  each milestone below, the "Tests" subsection lists tests to write
  before or alongside the corresponding feature code. Milestone
  acceptance requires these tests green.

### 5.5 What we deliberately don't test

- Browser audio playback (manual QA).
- `MediaRecorder` (browser-only; manual QA).
- Actual ffmpeg binary output byte-for-byte (too brittle).
- Third-party attribution strings (static).

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
|---|---|
| `server/__init__.py` | Package marker (empty). |
| `server/app.py` | Entry point. Argparse (`--port`, `--repo-root`), tool probe, `ThreadingHTTPServer`, route table, static-file handler. |
| `ui/index.html` | Four-zone skeleton: top bar, left panel, centre panel, bottom meter zone. Placeholders only. |
| `ui/main.js` | ES-module entrypoint. Fetches `/api/health`, renders tool-status banner. |
| `ui/styles.css` | CSS grid for the four zones, dark palette, basic typography. |
| `tests/__init__.py` | Empty. |
| `tests/test_app.py` | Health endpoint + static-file route tests. |
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
|---|---|---|---|
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

### 7.4 Tests (write alongside)

- `test_health_ok_when_tools_present` — monkeypatch `shutil.which` to
  return truthy, assert 200 + payload shape.
- `test_health_flags_missing_ffmpeg` — monkeypatch `which('ffmpeg')`
  to None, assert `tools.ffmpeg == false`.
- `test_index_served_at_root` — GET `/`, assert 200 and
  `Content-Type: text/html`.
- `test_static_traversal_rejected` — GET `/ui/../../etc/passwd`,
  assert 400 or 404 (not 200).

### 7.5 Acceptance

- `python3 -m server.app --port 8766` starts without error.
- `curl http://localhost:8766/api/health` returns expected JSON.
- Chrome loads `http://localhost:8766/`; four zones visible; health
  banner reflects reality (try `PATH=/ python3 -m server.app` to
  force missing tools).
- `python3 -m unittest discover tests` passes.

---

## 8. Milestone 2 — Bank listing + phoneme list render

**Goal:** With a seed bank present on disk, the UI shows the bank in
the top-bar dropdown, renders its phoneme list in the left panel, and
displays the privacy badge correctly. Selecting a phoneme shows its
IPA glyph and example word in the centre panel. No recording yet.

### 8.1 Files created

| Path | Role |
|---|---|
| `server/schema.py` | `validate_config(config: dict) -> list[str]` returns list of errors (empty on success). `REQUIRED_FIELDS`, `PRIVACY_VALUES`, `PHONEME_FIELDS` as module constants. |
| `server/banks.py` | `list_banks(repo_root) -> list[BankSummary]`; `read_bank(repo_root, bank_id) -> BankDetail`; raises `BankNotFound`, `BankInvalid`. |
| `server/state.py` | `read_state(bank_path) -> dict` (empty dict if missing or corrupt — corrupt file gets renamed to `state.json.corrupt-<ts>` per spec §14); `write_state(bank_path, state)` via temp-plus-rename. |
| `banks/en-au-leo/config.json` | Seed dev bank; `privacy: "private"`, ~10-phoneme subset for local dev. |
| `banks/en-au-leo/.gitignore` | `dist/` (private bank). |
| `banks/en-au-leo/raw/.gitkeep` | So the directory survives the gitignore. |
| `tests/test_schema.py` | Schema validation unit tests. |
| `tests/test_banks.py` | Bank discovery + read tests. |
| `tests/test_state.py` | Atomic state I/O + corrupt-file recovery tests. |
| `tests/fixtures/banks/en-test/config.json` | 3-phoneme fixture. |
| `tests/fixtures/banks/en-test/state.json` | Empty (no takes yet). |

### 8.2 Endpoints added

| Method | Path | Response |
|---|---|---|
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

### 8.5 Tests

- `test_schema.py`:
  - `test_valid_public_bank_passes`
  - `test_valid_private_bank_passes`
  - `test_missing_attribution_rejected_for_public`
  - `test_invalid_privacy_value_rejected`
  - `test_duplicate_phoneme_id_rejected`
  - `test_duplicate_ipa_rejected`
  - `test_non_slug_phoneme_id_rejected`
- `test_banks.py`:
  - `test_list_banks_empty_returns_empty_list`
  - `test_list_banks_skips_non_directories`
  - `test_list_banks_skips_folder_without_config`
  - `test_read_bank_returns_config_and_state`
  - `test_read_bank_with_invalid_config_raises`
- `test_state.py`:
  - `test_read_state_missing_returns_empty`
  - `test_read_state_corrupt_renames_and_returns_empty`
  - `test_write_state_is_atomic` (write to a path, kill mid-write simulated via patching `os.replace` to raise, assert target unchanged)

### 8.6 Acceptance

- `/api/banks` returns `en-au-leo`.
- `/api/banks/en-au-leo` returns the seed config + empty state.
- UI shows the bank, the phoneme list, the IPA detail, and the red
  "Private" badge.
- All tests green.

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
|---|---|
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
