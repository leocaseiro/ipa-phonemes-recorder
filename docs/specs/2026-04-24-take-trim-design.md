# Take Trim — Design Spec

**Date:** 2026-04-24
**Status:** Validated (awaiting implementation plan)
**Owner:** Leo Caseiro
**Base branch:** `feat/new-bank-flow`

## Summary

Add a non-destructive trim feature to recorded takes. The user drags
start/end handles (and nudges them via buttons/shortcuts) on the
existing `.take-waveform` canvas, previews the trimmed selection in
the browser, and, when happy, saves it as a **new** take in the same
phoneme. The source WAV is never modified. In-progress trim state
survives navigation and page reload via `localStorage`; an unsaved
edit is signaled with a `●` indicator on the take row.

## Motivation

Recorded takes frequently have dead air at the start (mic pickup,
breath, click) or trailing silence at the end. Re-recording to fix
this is expensive — especially for phonemes that are hard to voice
cleanly. A trim step lets the user keep the good middle of a take
without losing the original (important for children's voice
recordings, which must never be silently replaced or overwritten).

## User flow

1. User selects a take. The existing take waveform renders.
2. Trim handles appear at `start=0`, `end=duration` (full range).
3. User drags handles, nudges with buttons/shortcuts, or sets
   start/end from the playhead (`[` / `]`).
4. At any point the user can `P` to hear just the `[start..end]`
   region, or `Space` to hear the full take.
5. User may `Cmd+Z` / `Cmd+Shift+Z` through their edit history.
6. When happy, `S` (or the **Save** button) creates a new take via a
   server-side ffmpeg trim. The source take is untouched.
7. The new take appears in the list. The `●` on the source is cleared.

Navigating away from the take (another phoneme, another take, another
bank) preserves in-progress handle positions and history. The `●`
persists on the source row until either Save or an explicit Reset
(✕).

## UI layout

All new UI lives in the existing take detail panel, below the take
list.

### Waveform canvas

- Two draggable vertical handles: `start` (left) and `end` (right).
- A thin vertical `playhead` line between them.
- Regions outside `[start..end]` are rendered dimmed (half alpha).
- Handle grab zones are ≥ 8 px wide for easy mouse targeting.

### Trim bar (below the canvas)

Button row, left → right:

| Button | Action | Shortcut |
| --- | --- | --- |
| ⏮ | Jump playhead to clip start | `Home` |
| « | Nudge playhead −100 ms | `Shift+←` |
| ‹ | Nudge playhead −10 ms | `←` |
| `[` | Set trim **start** at playhead | `[` |
| ▶sel | Play trimmed selection | `P` |
| `]` | Set trim **end** at playhead | `]` |
| › | Nudge playhead +10 ms | `→` |
| » | Nudge playhead +100 ms | `Shift+→` |
| ⏭ | Jump playhead to clip end | `End` |
| ↶ | Undo last trim edit | `Cmd/Ctrl+Z` |
| ↷ | Redo | `Cmd/Ctrl+Shift+Z` |
| ✕ | Reset trim to full range (clears history) | (button only) |
| 💾 Save | Write new take from `[start, end]` | `S` |

### Additional shortcuts

- `,` / `.` — jump playhead to trim start / trim end.
- `Alt+←` / `Alt+→` — nudge the **nearest** handle (start if playhead
  is in the left half, end in the right) by 10 ms.
- `Alt+Shift+←` / `Alt+Shift+→` — same, 100 ms.

### Existing shortcuts preserved

`R` record, `Space` play full take, `Enter` keeper, `Backspace`
delete, `G` reference, `E` export, `ArrowUp`/`ArrowDown` phoneme
navigation. Nothing collides.

### Take-list dirty indicator

Take rows with unsaved trim edits render a small `●` indicator
prepended to the take id (inside `.takes-item__id`, or as an
adjacent span). Clean rows render unchanged.

## Data model

### In-memory trim state (client)

Module-level `Map<string, TrimState>`, keyed by
`` `${bankId}/${phonemeId}/${takeId}` ``:

```js
{
  durationMs: 2400,                       // from take metadata, immutable
  startMs: 180,                           // current trim start
  endMs: 2100,                            // current trim end
  playheadMs: 180,                        // current playhead
  history: [ { startMs, endMs }, ... ],   // initial entry is full range
  cursor: 3,                              // index into history
}
```

### What pushes history

- Drag-end (mouseup).
- Any nudge (button or shortcut).
- `[` / `]` setting start/end from playhead.
- Reset (pushes a synthetic full-range entry AND clears the stack).

Playhead moves do **not** push history. Live drag updates
`startMs`/`endMs` in state but pushes only on release.

### Redo semantics

Standard editor behavior: a new edit at a mid-stack cursor discards
entries after the cursor.

### History cap

100 entries per take. Beyond that, drop oldest. Prevents runaway
localStorage growth during a long session.

### Dirty flag

`isDirty = cursor > 0`. Drives the `●` in the take list.

### localStorage schema

Key: `ipa-trim:${bankId}`. Value:

```json
{
  "<phonemeId>/<takeId>": {
    "startMs": 180,
    "endMs": 2100,
    "history": [ { "startMs": 0, "endMs": 2400 }, ... ],
    "cursor": 3
  }
}
```

- Written debounced (300 ms) after any state change.
- Written immediately on `beforeunload`.
- Loaded once on bank select.
- Pruned when:
  - A take is deleted.
  - A save-as-duplicate succeeds for that take (entry removed).
- Stale-entry guard on load: drop entries whose `(phonemeId, takeId)`
  no longer exists in the bank state, or whose `endMs > durationMs`.

### Cross-tab concurrency

Not handled. Same scope as the rest of the app (single local
session).

## Server

### New endpoint

```
POST /api/banks/:bankId/phonemes/:phonemeId/takes/:takeId/trim
Content-Type: application/json
Body: { "start_ms": 180, "end_ms": 2100 }
→ 201 Created
  {
    "id": "take-004",
    "duration_ms": 1920,
    "peak_db": -16.7,
    "rms_db": -24.3,
    "created_at": "2026-04-24T12:00:00Z",
    "source_take_id": "take-003"
  }
```

### Validation

- `0 ≤ start_ms < end_ms ≤ source.duration_ms`
- `end_ms - start_ms ≥ 10` (one nudge step — zero-length is an error)

Violation → 400 with code `trim_invalid_range`.

### ffmpeg invocation

```
ffmpeg -y -i <source.wav> -ss <start_s> -to <end_s>
       -ar 48000 -ac 1 -c:a pcm_s16le <dest.wav>
```

Re-encode (not `-c copy`). At 48 kHz mono PCM the cost is negligible
and it guarantees sample-accurate boundaries plus bit-identical
format to recordings (no format drift between recorded and trimmed
takes).

### State update

- Next take id via existing `next_take_id` (monotonic, never reused).
- Metadata via existing `compute_peak_rms`.
- Append to `state.phonemes[pid].takes` with a new field
  `source_take_id` = the source take id.
- Bump `max_take_id`.
- `notes` defaults to empty string (not copied from source).

### Schema change

[server/schema.py](../../server/schema.py): add optional
`source_take_id` to the take entry validator. Type `str`, must match
`^take-\d{3,}$`, not required. Existing takes without the field stay
valid.

### Refactor done as part of this change

The ffmpeg → measure → append-to-state tail of
[server/takes.py](../../server/takes.py)'s `save_take` is duplicated
by the new `trim_take`. Extract the shared helper so both flows call
one function. Targeted improvement only — no unrelated refactor.

### What the server explicitly does NOT do

- No server-side trim history.
- No in-place trim (source WAV is never modified).
- No auto-delete of the source take after trim.

### Error codes

Reuses existing `TakeSaveFailed` codes: `ffmpeg_failed`,
`ffmpeg_timeout`, `wav_unreadable`. New code:
`trim_invalid_range`.

## Safety

- Children's-voice originals are never modified or deleted
  automatically.
- Trim is a local-only operation: it does not bypass the privacy
  gitignore. The new take inherits the bank's privacy flag via the
  existing gitignore sync (no new code path).
- `source_take_id` is provenance only — it has no effect on export.

## QA

Manual QA only (per project testing preference). No new automated
tests. The existing export-manifest golden-file test must continue
to pass unchanged.

### Manual checklist

1. Select a take → drag start handle → release → `●` appears on that
   take row.
2. Nudge with `←` / `→` / `Shift+←` / `Shift+→` → handles and
   playhead update; values match the ms counter.
3. `Cmd+Z` walks back through each nudge/drag; `Cmd+Shift+Z` redoes.
   A new edit mid-stack truncates future redos.
4. Navigate to another phoneme and back → handles restored; `●` still
   present.
5. Reload the browser → handles restored from localStorage; `●` still
   present.
6. `P` plays only the `[start..end]` region; `Space` still plays the
   full take.
7. `S` → new `take-NNN` appears in the list; `●` on the source is
   cleared; localStorage entry for the source take is gone.
8. `ffprobe` the new WAV — duration matches `end_ms − start_ms` within
   ±10 ms, 48 kHz mono pcm_s16le.
9. Delete the source take → trimmed child stays. Its
   `source_take_id` still points to the (now-gone) id; that's
   intentional provenance.
10. Force a bad body via DevTools (`start_ms ≥ end_ms`) → 400
    `trim_invalid_range`.
11. Export the bank → trimmed takes export like any other take;
    manifest golden-file test passes unchanged.

## Files touched

- [ui/main.js](../../ui/main.js) — trim-bar HTML, handle drawing on
  the take-waveform canvas, drag / nudge / shortcut handlers,
  history stack, localStorage I/O, `●` indicator on take rows.
- [ui/audio.js](../../ui/audio.js) — add
  `playRange(buffer, startMs, endMs)` alongside existing
  `playBuffer`.
- [ui/styles.css](../../ui/styles.css) — handle / playhead styles,
  trim-bar layout, `●` indicator.
- [ui/api.js](../../ui/api.js) — `postTrim(bankId, phonemeId,
  takeId, startMs, endMs)`.
- [server/app.py](../../server/app.py) — route registration and
  handler for `POST …/trim`.
- [server/takes.py](../../server/takes.py) — new `trim_take()` plus
  extracted shared helper for the ffmpeg → measure → state tail.
- [server/schema.py](../../server/schema.py) — accept optional
  `source_take_id` on take entries.

## Out of scope / follow-ups

- `?` / `Shift+?` shortcuts cheatsheet dialog. Deferred by user
  request; do after trim lands.
- Multi-segment cuts, fades, silence detection / auto-trim.
- Undoing a save-as-duplicate beyond the existing 🗑 button on the
  new take.
- Persisting trim state into `state.json` or across machines
  (declined — localStorage is sufficient).
- Cross-tab concurrency.
