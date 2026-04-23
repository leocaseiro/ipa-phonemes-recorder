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

## Table of contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Target project structure](#3-target-project-structure)
4. [Conventions](#4-conventions)
5. [Testing strategy](#5-testing-strategy)
6. [Phoneme inventory seed](#6-phoneme-inventory-seed)
7. [Milestone 1 — Server skeleton + hello-world UI](#7-milestone-1--server-skeleton--hello-world-ui)
8. [Milestone 2 — Bank listing + phoneme list render](#8-milestone-2--bank-listing--phoneme-list-render)
9. [Milestone 3 — Microphone capture, meter, waveform](#9-milestone-3--microphone-capture-meter-waveform)
10. [Milestone 4 — Take recording](#10-milestone-4--take-recording)
11. [Milestone 5 — Take playback, keeper selection, delete](#11-milestone-5--take-playback-keeper-selection-delete)
12. [Milestone 6 — Reference audio](#12-milestone-6--reference-audio)
13. [Milestone 7 — Export pipeline](#13-milestone-7--export-pipeline)
14. [Milestone 8 — Privacy flag + per-bank `.gitignore`](#14-milestone-8--privacy-flag--per-bank-gitignore)
15. [Milestone 9 — New-bank flow + polish](#15-milestone-9--new-bank-flow--polish)
16. [Risks & open questions](#16-risks--open-questions)
17. [Completion tracker](#17-completion-tracker)

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
