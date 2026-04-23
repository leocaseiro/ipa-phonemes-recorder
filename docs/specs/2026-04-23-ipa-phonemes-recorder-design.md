# IPA Phonemes Recorder — Design Spec

**Date:** 2026-04-23
**Status:** Validated (awaiting implementation plan)
**Owner:** Leo Caseiro

## 1. Purpose

A small, local desktop tool that lets a person (the **speaker**) record
their own voice saying IPA phoneme sounds, organise the recordings into
**banks** (one bank per language/accent/speaker combo), and export each
bank as a drop-in soundfont bundle for phonics apps — specifically
[BaseSkill](https://github.com/leocaseiro/base-skill).

The primary motivation is to replace eSpeak-NG synthetic phonemes in
BaseSkill with a warm, natural human voice that blends well, while
keeping a path open for additional languages, accents, and voice
contributors over time.

## 2. Goals

- Record one or more takes of each IPA phoneme in a bank.
- Play a reference clip (Wikimedia Commons IPA audio or eSpeak-NG
  synthesis) so the speaker can match the target sound.
- Let the speaker mark a **keeper take** per phoneme.
- Export a bank to the exact file format BaseSkill consumes at
  `public/audio/phonemes.{mp3,json}` — zero changes required on the
  BaseSkill side.
- Support multiple banks in the same repo (different languages, accents,
  or speakers) without code changes — banks are pure data.
- Make it trivial to add, remove, or re-record phonemes at any time.
- Default to privacy-preserving behaviour: new banks are private;
  recordings never get accidentally published.

## 3. Non-goals (explicit out-of-scope for v1)

- **Diphone / whole-word synthesis.** The tool produces per-phoneme
  audio only. Concatenative TTS is a future extension.
- **Short-vs-long variant tracks per phoneme.** A single keeper per
  phoneme is enough; the `loopable` flag (see §6) covers sustained
  sounds.
- **In-browser waveform editing (trim handles, fades).** Trimming and
  loudness-matching happen in the export step via ffmpeg filters. If a
  take is bad, re-record.
- **Mobile or web-hosted version.** Desktop-only, localhost-only tool.
- **Cloud sync, multi-device, collaboration.** Personal tool on a
  single machine.
- **Automatic accent detection / speaker identification.** The bank is
  tagged manually in its `config.json`.
- **Integration CI with BaseSkill.** The handoff is a manual copy of
  two files (`phonemes.mp3` + `phonemes.json`).

## 4. Target users

- **Primary:** the repo owner recording their own voice.
- **Secondary:** household members (including children) whose
  recordings stay private by design.
- **Tertiary:** open-source contributors who fork the repo to record
  their own voice banks — the tool's code is MPL-2.0 so the fork
  workflow is friction-free.

## 5. Compatibility target: BaseSkill

BaseSkill consumes a single MP3 sprite plus a JSON manifest:

- `public/audio/phonemes.mp3` — MP3, MPEG-1 Layer III / Layer III v2,
  **22.05 kHz mono**, variable-bitrate target ~56 kbps. All phonemes
  concatenated into one file.
- `public/audio/phonemes.json` — a flat JSON object keyed by literal
  IPA characters:

  ```json
  {
    "ʃ": { "start": 45950, "duration": 420, "loopable": true },
    "k": { "start": 15851, "duration": 90 },
    "tʃ": { "start": 62010, "duration": 310 }
  }
  ```

  - `start` — millisecond offset into the sprite.
  - `duration` — millisecond length of the phoneme segment.
  - `loopable` (optional boolean) — if `true`, BaseSkill loops the
    segment seamlessly for sustained playback (used for fricatives and
    long vowels).

Any export from this tool **must** match this shape exactly. Keys are
raw Unicode IPA characters (not ASCII slugs, not ARPAbet, not numeric
IDs). BaseSkill performs no schema validation and no fallback — a
mismatch means silent playback failure.

## 6. Domain model

### 6.1 Bank

A **bank** is one (language, accent, speaker) tuple. Each bank owns:

- A phoneme inventory (list of IPA symbols the speaker intends to
  record).
- All recorded takes for those phonemes.
- A keeper selection per phoneme.
- A privacy flag (`public` or `private`).
- An attribution string (used when privacy is `public`).
- An optional target loudness (default −16 LUFS).

Banks are entirely data-driven. A new bank is just a new folder.

### 6.2 Phoneme entry

A phoneme entry in a bank's `config.json` declares:

- `id` — ASCII-safe slug used for filenames (e.g., `sh`, `th_vl`).
- `ipa` — canonical Unicode IPA symbol used as the manifest key (e.g.,
  `ʃ`, `θ`).
- `example` — a short example word shown in the UI (e.g., `"ship"`).
- `loopable` — boolean; whether the phoneme is a sustainable/
  continuant sound. Fricatives, nasals, approximants, and long vowels
  are typically `true`; stops and affricates `false`.
- `category` (optional) — `"vowel"` or `"consonant"` or a finer tag,
  used for grouping in the UI.

### 6.3 Take

A take is one recorded attempt at a phoneme. It has:

- A WAV file stored at
  `banks/<bank>/raw/<phoneme-id>/take-NNN.wav`, where `NNN` is a
  zero-padded three-digit integer that is monotonically increasing
  within that phoneme's take folder. Take IDs never get reused after
  deletion — if `take-002` is deleted, the next recording is
  `take-003`, not `take-002`.
- Metadata recorded in `state.json`: creation timestamp, duration,
  detected peak amplitude, detected RMS or LUFS, and a user-set
  `notes` field (optional).
- A `keeper: true/false` flag at most one of which is true per
  phoneme.

### 6.4 State

`banks/<bank>/state.json` holds transient UI + session state:

- For each phoneme: the list of takes and which one is the keeper.
- Last-selected phoneme (for session restore).
- Last-used input device label (hint only; re-prompts on denied
  permission).

State autosaves on every meaningful user action.

## 7. Filesystem layout

```
ipa-phonemes-recorder/
├── LICENSE                  # MPL-2.0
├── README.md
├── CLAUDE.md
├── .gitignore               # Python/macOS + banks/*/raw + banks/*/state.json + references/
├── docs/
│   └── specs/
│       └── 2026-04-23-ipa-phonemes-recorder-design.md   # this file
├── scripts/
│   └── fetch-references.py  # one-shot Wikimedia IPA-audio downloader
├── server/
│   └── app.py               # stdlib HTTP server + filesystem glue
├── ui/
│   ├── index.html
│   ├── main.js
│   └── styles.css
├── banks/
│   ├── en-au-leo/
│   │   ├── config.json      # inventory + privacy + attribution
│   │   ├── .gitignore       # tool-managed; `dist/` if privacy=private
│   │   ├── raw/             # always gitignored
│   │   │   └── sh/
│   │   │       ├── take-001.wav
│   │   │       └── take-002.wav
│   │   ├── state.json       # always gitignored
│   │   └── dist/            # committed iff privacy=public
│   │       ├── phonemes.mp3
│   │       └── phonemes.json
│   └── en-au-kid-a/
│       ├── config.json      # privacy: "private"
│       ├── .gitignore       # contains: dist/
│       ├── raw/
│       ├── state.json
│       └── dist/            # gitignored by the per-bank .gitignore
├── references/              # gitignored; populated by fetch script
│   ├── ATTRIBUTION.md       # per-file CC-BY-SA credit
│   ├── sh.ogg
│   └── th_vl.ogg
└── tmp/                     # gitignored; ffmpeg scratch dir
```

Root `.gitignore` covers the always-gitignored paths. Each private bank
also has its own `.gitignore` (written by the tool) to gitignore
`dist/`. Git respects nested `.gitignore` files, so private banks
cannot leak even if a user accidentally commits with `git add banks/`.

## 8. Configuration schemas

### 8.1 `banks/<bank>/config.json`

```json
{
  "name": "Aussie English — Leo",
  "locale": "en-AU",
  "speaker": "Leo Caseiro",
  "privacy": "public",
  "attribution": "Leo Caseiro, CC BY 4.0",
  "target_lufs": -16,
  "phonemes": [
    { "id": "sh",    "ipa": "ʃ",  "example": "ship",  "loopable": true,  "category": "consonant" },
    { "id": "th_vl", "ipa": "θ",  "example": "thin",  "loopable": true,  "category": "consonant" },
    { "id": "k",     "ipa": "k",  "example": "kite",  "loopable": false, "category": "consonant" },
    { "id": "ee",    "ipa": "iː", "example": "see",   "loopable": true,  "category": "vowel" }
  ]
}
```

Required fields: `name`, `locale`, `privacy`, `phonemes`. Other fields
are optional with sensible defaults.

`privacy` is one of `"public"` or `"private"` (any other value is
rejected). `target_lufs` defaults to `-16`. `attribution` is required
if and only if `privacy == "public"`.

### 8.2 `banks/<bank>/state.json`

```json
{
  "last_phoneme_id": "sh",
  "last_input_device": "MacBook Pro Microphone",
  "phonemes": {
    "sh": {
      "keeper_take": "take-002",
      "takes": [
        {
          "id": "take-001",
          "created_at": "2026-04-23T10:14:00Z",
          "duration_ms": 642,
          "peak_db": -2.3,
          "rms_db": -18.1,
          "notes": ""
        },
        {
          "id": "take-002",
          "created_at": "2026-04-23T10:15:17Z",
          "duration_ms": 701,
          "peak_db": -1.8,
          "rms_db": -16.9,
          "notes": "cleaner attack"
        }
      ]
    }
  }
}
```

### 8.3 `banks/<bank>/dist/phonemes.json`

Must match BaseSkill's expected shape (see §5). Emitted from the
export step; should never be hand-edited.

## 9. Architecture

### 9.1 Stack

- **Server:** Python 3.10+ stdlib (`http.server`, `json`, `wave`,
  `subprocess`). No pip, no venv. Runs on `localhost:<PORT>` (default
  8766, one above the existing phoneme-tuner port).
- **UI:** plain HTML + vanilla JS + CSS, served by the same server.
  No bundler, no framework. Uses `MediaRecorder` + `AudioContext` for
  mic capture, metering, and waveform display.
- **Audio workers:** `ffmpeg` and `espeak-ng`, invoked via
  `subprocess`, both required on `PATH`.

### 9.2 Server responsibilities

- Serve the UI (`GET /`, `GET /ui/*`).
- List banks (`GET /api/banks`) by scanning `banks/`.
- Read a bank's config + state (`GET /api/banks/:id`).
- Accept a recorded take (`POST /api/banks/:id/phonemes/:pid/takes`)
  — body is WebM/Opus; server transcodes to WAV via ffmpeg and
  stores under `raw/<pid>/take-NNN.wav`.
- Read a take's WAV (`GET /api/banks/:id/phonemes/:pid/takes/:tid`).
- Delete a take (`DELETE ...`).
- Update state (`PUT /api/banks/:id/state`) — e.g., set keeper take,
  update notes.
- Play a reference (`GET /api/banks/:id/phonemes/:pid/reference`) —
  returns the Wikimedia OGG if present in `references/`, else
  synthesises via eSpeak-NG.
- Export a bank (`POST /api/banks/:id/export`) — runs the pipeline in
  §12 and writes `dist/phonemes.mp3` + `dist/phonemes.json`.
- Create a new bank (`POST /api/banks`) — writes the folder skeleton
  with a template config (privacy defaults to `"private"`) and the
  per-bank `.gitignore`.

State changes are written atomically: write to `state.json.tmp`, then
`os.rename` onto `state.json`. No partial writes survive a crash.

### 9.3 UI responsibilities

See §10.

## 10. Recorder UI

### 10.1 Layout (four zones)

- **Top bar:** bank dropdown + "New bank" + "Export bank" + privacy
  badge (green "Public" or red "Private") showing the current bank's
  state.
- **Left panel:** scrollable phoneme list. Each row: IPA symbol,
  example word, and a status glyph —
  - `○` never recorded
  - `●` has takes but no keeper selected
  - `✓` keeper selected

  `↑` and `↓` navigate the list.

- **Centre panel:** selected phoneme detail —
  - Large IPA glyph + example word.
  - "Play reference" button (`G`) that plays the Wikimedia OGG or
    eSpeak fallback; brief attribution line displayed during playback.
  - Waveform of the currently selected take (rendered via Web Audio
    `AudioBuffer`).
  - Takes list: each row shows take id, duration, peak dB, RMS dB, a
    "Play" button, and a radio-style "Keeper" selector. `Enter` marks
    the currently-selected take as keeper; `Backspace` deletes it.

- **Bottom zone:** always-on microphone level meter (VU bar from Web
  Audio `AnalyserNode`). Below it, a big circular Record button.
  - `R` toggles recording.
  - `Space` plays the currently selected take.

### 10.2 Keyboard shortcuts

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate phoneme list |
| `R` | Start / stop recording |
| `Space` | Play current take |
| `Enter` | Mark current take as keeper |
| `Backspace` | Delete current take (with one-step confirm) |
| `G` | Play reference audio |
| `E` | Export current bank |

### 10.3 Autosave

Every meaningful action (mark keeper, delete, add note, record) PUTs
the new state server-side before acknowledging. Failure rolls back the
UI optimistic update.

## 11. Reference audio pipeline

### 11.1 Fetch script

`scripts/fetch-references.py` is a one-shot downloader. It reads a
static list of (phoneme-id, Wikimedia URL, attribution) triples,
downloads each OGG into `references/<phoneme-id>.ogg`, and appends a
row to `references/ATTRIBUTION.md` with licence + uploader credit.

The script is idempotent (skips already-downloaded files) and
tolerates partial runs. The URL list is embedded in the script as a
constant, extracted from the
[IPA consonant chart with audio](https://en.wikipedia.org/wiki/IPA_consonant_chart_with_audio)
and the equivalent vowel-chart page.

### 11.2 eSpeak-NG fallback

When the UI requests a reference for a phoneme whose OGG isn't present
in `references/`, the server invokes `espeak-ng` with the appropriate
Kirshenbaum code and streams the generated audio back to the browser.

### 11.3 Isolation from export

Reference audio **must not** enter the export pipeline under any
condition. The export reads only from `banks/<bank>/raw/`, and the
`references/` directory is never opened during export. This is a
hard-coded guarantee, not a best-effort policy; automated tests check
the export step never reads outside the bank root.

## 12. Export pipeline

Triggered by `POST /api/banks/:id/export`.

1. **Read** `banks/<bank>/config.json` and `state.json`.
2. **Collect keepers:** for each phoneme in `config.json.phonemes`,
   look up `state.json.phonemes[id].keeper_take`. If no keeper is set,
   either (a) skip that phoneme with a warning, or (b) fail the export
   — chosen via an `on_missing_keeper: "skip" | "fail"` option in the
   export request (default `"skip"`).
3. **For each keeper WAV**, run an ffmpeg filter chain:
   - `silenceremove=stop_periods=-1:stop_duration=0.05:stop_threshold=-50dB`
     — trim leading/trailing silence.
   - `loudnorm=I=<target_lufs>:TP=-1.5:LRA=11` — loudness-normalise to
     the bank's `target_lufs` (default −16).
   - Resample to 22.05 kHz mono (`-ar 22050 -ac 1`).
   - Write an intermediate WAV.
4. **Concatenate** the intermediates with small silent gaps
   (25 ms) using `ffmpeg concat` demuxer. Track cumulative millisecond
   offsets as each segment is appended.
5. **Encode** the concatenated WAV as MP3:
   - `-c:a libmp3lame -q:a 6 -ar 22050 -ac 1` (VBR ~56 kbps), matching
     BaseSkill's existing sprite.
6. **Emit manifest:** a JSON object keyed by `phoneme.ipa` →
   `{ start, duration, loopable }` where `loopable` is copied from the
   phoneme's config entry.
7. **Write** `dist/phonemes.mp3` and `dist/phonemes.json`.
8. **Safety gate:** if the bank's `privacy == "private"`, verify the
   bank's local `.gitignore` contains `dist/`. If missing, the tool
   rewrites it before writing any output.
9. Return a summary to the UI (phoneme count, total duration, output
   file sizes, any warnings).

The intermediate WAVs go in `tmp/` and are cleaned up after success.

## 13. Privacy model

### 13.1 Per-bank flag

Each bank declares its own privacy in `config.json`. Default for newly
created banks is `"private"`. Flipping from private to public is a
one-field edit but is surfaced in the UI with an explicit confirm
dialog, and the tool rewrites the bank's `.gitignore` immediately.

### 13.2 Gitignore enforcement

Root `.gitignore` always ignores `banks/*/raw/`, `banks/*/state.json`,
and `references/`.

Per-bank `.gitignore` is generated and owned by the tool:

- Private bank: contains `dist/`.
- Public bank: empty or absent.

On every bank read, the tool compares the file's contents with the
expected state given `privacy` and warns (and optionally auto-fixes)
drift.

### 13.3 Child-voice defaults

Because voice is biometric data and CC-BY-4.0 is effectively
irrevocable once published, the documented default is to keep
children's banks private indefinitely. The UI surfaces this stance
prominently:

- On the "New bank" form, a short note explains the risk and confirms
  that the default privacy is `private`.
- On every export preview targeting a bank whose `privacy` is being
  flipped from `private` to `public`, a blocking confirmation asks the
  user to affirm informed consent from the speaker — and for minor
  speakers, from their guardian.

The privacy flag is the single source of truth; no secondary "minor"
field is added to the schema. Enforcement is by the privacy flag and
the per-bank `.gitignore` — the rest is documented guidance.

## 14. Error handling & edge cases

- **Microphone permission denied.** UI shows a banner with
  platform-specific re-prompt instructions.
- **Missing `ffmpeg` or `espeak-ng` on PATH.** Server startup prints
  a clear error and refuses to serve; the UI can detect this via a
  `GET /api/health` endpoint and display the missing tools.
- **Corrupt `state.json`.** On read failure, the server renames the
  file to `state.json.corrupt-<ts>` and starts with a fresh empty
  state, logging a warning. Raw WAVs are untouched so nothing is lost.
- **Orphaned WAV** (take file with no state entry): the UI shows it as
  an "orphan" with a button to adopt it into state or delete it.
- **Export with zero keepers.** Returns 400 with a clear message; no
  partial write.
- **Disk full.** Export fails with a clear error; existing `dist/`
  files are untouched (writes are atomic via temp-plus-rename).
- **Two browser tabs open.** Last write wins; not worth solving for a
  single-user tool.

## 15. Testing approach

- **Unit tests (Python stdlib `unittest`):**
  - Bank loader: accepts valid configs, rejects invalid ones.
  - Manifest emitter: given a fixture of keeper WAVs and a config,
    produces a manifest matching BaseSkill's schema. Golden-file
    comparison.
  - Slug / IPA round-trip: every phoneme id in the standard English
    bank maps back to the correct Unicode symbol.
  - Gitignore enforcement: changing `privacy` updates the per-bank
    `.gitignore`; drifted files are detected.
  - Reference isolation: a mocked export attempt that tries to read
    from `references/` raises.

- **Manual audio QA:**
  - Record a short bank (5 phonemes), export, drop into
    `base-skill/public/audio/`, verify playback in BaseSkill's
    `WordLibraryExplorer` story.

- **No browser automation for v1.** The UI is a personal tool; adding
  Playwright would exceed the scope.

## 16. Implementation order (rough — to be refined in the plan)

1. Stdlib server skeleton + hello-world UI.
2. Bank listing, config.json loading, phoneme list rendering.
3. Microphone capture + live level meter + waveform display.
4. Take recording: POST to server, store WAV, update state.
5. Take playback + keeper selection + delete.
6. Reference audio — fetch script + server endpoint + UI button +
   eSpeak fallback.
7. Export pipeline — ffmpeg chain, manifest emission, isolation tests.
8. Privacy flag + per-bank `.gitignore` management.
9. "New bank" flow + UI polish + keyboard shortcuts + autosave.

Milestones 1–4 deliver a recording-capable prototype. 5–7 make it
useful end-to-end. 8–9 add the safety and UX layers.

## 17. Future extensions (not in v1)

- **Diphones** — record phoneme-pair transitions for more natural
  concatenative synthesis. Same bank model, ~1500 additional units.
- **Short / long variant tracks** — explicit per-phoneme short and
  long keepers exported as `"ʃ": { "short": {...}, "long": {...} }`.
  Requires a BaseSkill-side change to consume.
- **Multi-bank UI** — a BaseSkill-side "pick your accent" setting, so
  users can swap between banks at runtime. The recorder tool is
  already bank-aware; BaseSkill needs the loader change.
- **Import / export banks as zips** — frictionless sharing of public
  banks between contributors.
- **Per-take trim handles in the browser** — the Web Audio + canvas
  work is small but non-trivial; deferred until the zero-UI-editing
  flow proves insufficient.
- **Automated pre-push gate** — symlink `dist/` into a BaseSkill
  worktree so exports flow automatically. Nice-to-have.
