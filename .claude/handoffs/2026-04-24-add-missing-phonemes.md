# Handoff: add missing phonemes to en-au-leo (schwa, ʒ, əʊ, ʊə)

**Date:** 2026-04-24
**Branch:** `feat/new-bank-flow`
**Git status:** clean (6 untracked `.specstory/` churn, ignore)
**Commits ahead of master:** 2 (M9 landed locally, not yet merged)
**Last commit:** `2d81dac feat(ui): New bank button + modal form + wiring`
**PR:** none (this project does not use GitHub PRs yet)

## Resume command

```
cd ~/Sites/ipa-phonemes-recorder
python3.11 -m server.app   # run the app while editing
```

Then open this handoff and work through §"Plan".

## Current state

**Task:** the user tried to voice `surprise /səˈpraɪz/` in British English and hit a blocker — **`ə` (plain schwa) is not in the bank inventory**. Separate audit revealed a second missing consonant (`ʒ`, "measure") and a British diphthong gap (`əʊ`, British goat). `ʊə` (cure) is a nice-to-have.
**Phase:** scoped + audited; not yet implemented.
**Progress:** 0 / 4 phonemes added.

## What we did

- Confirmed the IPA reading: the `sur-` in `/səˈpraɪz/` is `/ə/`, not `/ɜː/`, because the syllable is unstressed (English vowels reduce to schwa in unstressed positions). The `ˈ` is the primary-stress mark, not a phoneme.
- Audited the current 44-phoneme inventory in [banks/en-au-leo/config.json](../../banks/en-au-leo/config.json) against a standard English chart (GA + RP combined).
- Verified which reference files already exist under `references/polyu/` and which keys are mapped in `server/seeds/phoneme_polyu_files.json` and `phoneme_reference_files.json`.

## Decisions made

- **Add `ə` (schwa) as the top priority** — Why: it's the single most common English vowel, and without it any multi-syllable transcription collapses the moment it hits an unstressed syllable. How to apply: see §"Plan" below.
- **Add `ʒ` next** — Why: filling a real consonant gap (measure, vision, pleasure, genre). Both PolyU and vocab.com have files ready.
- **Add `əʊ` as a nice-to-have for British transcriptions** — Why: the bank is en-AU/British-leaning; RP "goat" is `/əʊ/`, not `/oʊ/`. The existing `ow = oʊ` can stay (it's valid GA); adding `əʊ` lets British dictionary entries map cleanly. How to apply: reuse PolyU `OH.mp3` (no British-specific recording exists in the set); the reference is close enough for a recording aid.
- **Defer `ʊə` (cure)** — Why: modern RP often collapses `/ʊə/` → `/ɔː/` (CURE → NORTH), and the phoneme is nearly extinct in younger speakers. Add only if the user finds a real-world word where they want to distinguish it. PolyU has `OO-ER.mp3` if we decide to add.

## Audit — full 44-phoneme coverage vs standard English chart

**Consonants (24 expected):** all present except **`ʒ`**.
**Monophthongs (11 expected):** all present except **`ə`**.
**Closing diphthongs (5 expected):** all present; British **`əʊ`** is absent (GA `oʊ` is present).
**Centring diphthongs (3 expected):** `ɪə` + `eə` + `ɛə` present (last two are effectively the same phoneme split by spelling — `there` vs `Mary`; harmless); **`ʊə`** absent.
**Other:** `juː`, `ks` digraphs present (unusual but fine).

| Missing phoneme | Example | PolyU file | Vocabulary.com file | Priority |
| --- | --- | --- | --- | --- |
| `ə` | about, surprise, comma | `SCHWA.mp3` | `mid_central-gqxn5h.mp3` | **now** |
| `ʒ` | measure, vision, pleasure | `ZH.mp3` | `zh-fy90bw.mp3` | **now** |
| `əʊ` | goat (RP) | reuse `OH.mp3` | reuse `o-c3q2rv.mp3` | nice-to-have |
| `ʊə` | cure, tour (conservative RP) | `OO-ER.mp3` | — (none on chart) | defer |

## Plan

Four steps per phoneme. Do all three priority phonemes in one commit if working.

### 1 — Add the phoneme entry to `banks/en-au-leo/config.json`

Append to the `phonemes` array (the schema accepts any order; alphabetical-by-id-ish fits existing style):

```json
{ "id": "schwa", "ipa": "ə",  "example": "about",   "loopable": true, "category": "vowel" },
{ "id": "zh",    "ipa": "ʒ",  "example": "measure", "loopable": true, "category": "consonant" },
{ "id": "oh",    "ipa": "əʊ", "example": "goat",    "loopable": true, "category": "diphthong" }
```

`id` values must match `^[a-z0-9_]+$` per `server/schema.py`. `loopable: true` for all three (they're sustainable sounds).

**Do not reuse `ow` for `əʊ`** — `ow` is already mapped to `oʊ`. Use a new id (`oh` proposed; `goat_rp` if you want it clearer).

### 2 — Map each phoneme to a PolyU file

Edit [server/seeds/phoneme_polyu_files.json](../../server/seeds/phoneme_polyu_files.json):

```json
"schwa": "SCHWA.mp3",
"zh":    "ZH.mp3",
"oh":    "OH.mp3"
```

### 3 — Map each phoneme to a Vocabulary.com file

Edit [server/seeds/phoneme_reference_files.json](../../server/seeds/phoneme_reference_files.json):

```json
"schwa": "mid_central-gqxn5h.mp3",
"zh":    "zh-fy90bw.mp3",
"oh":    "o-c3q2rv.mp3"
```

Both source files already live under `references/` (checked on disk — `ls references/ | grep -E 'mid_central|zh|o-c3q'` returns all three). **No fetch script run needed for these three.**

### 4 — Update the English-basic seed so new banks inherit the additions

Edit [server/seeds/english-basic.json](../../server/seeds/english-basic.json) — add the same three phoneme entries to `phonemes`. Keeps new-bank-flow (M9) in sync.

### 5 — Verify

```bash
python3.11 -m unittest tests.test_references   # still 7/7
python3.11 -m server.app
```

In the browser, select each new phoneme and press `G`. All three should play via PolyU (auto source picks PolyU first when present).

Then test-voice the word "surprise" by cycling through `s`, `schwa`, `p`, `r`, `ai`, `z` — all should play.

## Key files

- [banks/en-au-leo/config.json](../../banks/en-au-leo/config.json) — phoneme inventory for the primary bank
- [server/seeds/english-basic.json](../../server/seeds/english-basic.json) — default inventory for new banks (mirrors en-au-leo)
- [server/seeds/phoneme_polyu_files.json](../../server/seeds/phoneme_polyu_files.json) — phoneme_id → PolyU filename map
- [server/seeds/phoneme_reference_files.json](../../server/seeds/phoneme_reference_files.json) — phoneme_id → Vocabulary.com filename map
- [server/schema.py](../../server/schema.py) — validates config.json; rejects duplicate ids / duplicate IPAs, so don't reuse `ow` for `əʊ`
- [references/polyu/](../../references/polyu/) — 48 audio files; `SCHWA.mp3`, `ZH.mp3`, `OH.mp3`, `OO-ER.mp3` already present

## Open questions

- [ ] Should `əʊ` get its own PolyU recording or just reuse `OH.mp3`? The PolyU set does not include a British-specific `əʊ` file. Reusing `OH.mp3` is the pragmatic call; flag if user wants a dedicated recording later.
- [ ] Should the bank's existing `e_schwa` (eə, "there") and `e_near` (ɛə, "Mary") be collapsed into one phoneme? They share the same PolyU mapping already and are merged in modern RP. Not blocking.

## Context to remember

- **User is Aussie / British-leaning.** Don't add rhotic-variant American vowels (ɚ, ɝ). The bank intentionally has both `oʊ` (GA) and should gain `əʊ` (RP) for transcription flexibility.
- **The IPA `ˈ` is a stress mark, not a sound.** If you see it in the user's transcription, ignore it when picking phonemes to record.
- **Vowel reduction is the rule.** Unstressed syllables in English become schwa regardless of spelling (`sur-` in surprise, `a` in about, `er` in "teacher"). Without `ə`, >50% of English multisyllabic words can't be fully voiced.
- **Testing memory still applies** — this is a feature addition, not a bug fix, so no regression tests required. But running `python3.11 -m unittest discover tests` after the changes is cheap and catches seed-file schema drift.
- **Don't run a fetch script for the priority three** — all files are already on disk. Only `ʊə` might need a fetch (from PolyU, the `OO-ER.mp3` is already there too; vocab.com has no matching file).
- **M9 is unmerged.** Current branch `feat/new-bank-flow` has the New-bank UI + endpoint. When picking up this handoff, the user may merge M9 to master first or not — the phoneme changes don't depend on it.
