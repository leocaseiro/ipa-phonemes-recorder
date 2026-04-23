# Handoff: IPA phonemes recorder — spec ready for implementation plan

**Date:** 2026-04-23
**Repo:** `leocaseiro/ipa-phonemes-recorder` (greenfield, sibling of `base-skill`)
**Branch:** `docs/initial-design-spec`
**Git status:** clean, 0 unpushed
**Last commit:** `7b86444` docs: add initial design spec
**PR:** #1 — open — https://github.com/leocaseiro/ipa-phonemes-recorder/pull/1

## Resume command

```bash
cd ~/Sites/ipa-phonemes-recorder
# If PR #1 has merged: git checkout master && git pull --ff-only
# Otherwise stay on docs/initial-design-spec
```

Then, in a fresh Claude Code session launched from that directory:

> Read `docs/specs/2026-04-23-ipa-phonemes-recorder-design.md` and use
> the `superpowers:writing-plans` skill to produce an implementation plan.

## Current state

**Task:** Build a local macOS tool to record IPA phoneme sounds into
banks and export BaseSkill-compatible MP3 + JSON soundfonts.
**Phase:** design complete, awaiting implementation plan.
**Progress:** spec on PR #1; no source code written yet.

## What we did

Brainstormed the tool end-to-end with the user. Investigated
BaseSkill's existing phoneme playback (`src/data/words/phoneme-audio.ts`,
sprite at `public/audio/phonemes.{mp3,json}`) so the recorder can emit
drop-in output with zero changes on the consumer side. Created the new
public repo, scaffolded README / LICENSE (MPL-2.0) / CLAUDE.md /
.gitignore on `master`, committed the design spec on a branch, opened
PR #1 for review.

## Decisions made

- **Separate repo, not a tool inside BaseSkill** — the recorder is a
  standalone utility; user explicitly requested a fresh repo.
- **Python stdlib + plain browser UI** — matches the user's existing
  `tools/phoneme-tuner` convention in BaseSkill. No pip, no venv.
- **Bank-per-(locale, accent, speaker)** — banks are pure folders, so
  extending to more languages/accents is `mkdir + config.json`, no
  code changes.
- **Licensing split:** code MPL-2.0; public bank recordings CC-BY-4.0;
  private banks stay local. User owns recordings outright and can use
  them in a closed premium app regardless of public license.
- **Privacy default `"private"`** for new banks. Voice is biometric
  data; CC-BY-4.0 is effectively irrevocable once published. Child
  voices should stay private unless explicit, informed, long-term
  consent is given.
- **Per-bank tool-managed `.gitignore`** — private banks' `dist/` is
  gitignored locally; public banks' `dist/` is committed.
- **Reference audio isolated from export** — Wikimedia Commons
  CC-BY-SA OGGs are a recording aid only; the export pipeline reads
  only from `banks/<bank>/raw/` and never touches `references/`.
- **Single keeper per phoneme** in v1; `loopable` flag handles
  sustained sounds (fricatives, long vowels) by letting BaseSkill
  loop-seamlessly. No separate short/long take tracks in v1.
- **No in-browser audio editing** — ffmpeg silence-trim + `loudnorm`
  in the export step. Re-record if a take is bad.
- **Port 8766** for the server, one above the existing
  phoneme-tuner at 8765.

## Spec

- [`docs/specs/2026-04-23-ipa-phonemes-recorder-design.md`](../../docs/specs/2026-04-23-ipa-phonemes-recorder-design.md)
  — 17 sections. Authoritative input for the implementation plan.

## Key files in this repo

- `docs/specs/2026-04-23-ipa-phonemes-recorder-design.md` — the spec.
- `CLAUDE.md` — conventions (MPL-2.0 header per source file,
  branch-per-PR, TDD for bug fixes, child-voice safety rails).
- `.gitignore` — `banks/*/raw/`, `banks/*/state.json`, `references/`
  always ignored at root; private banks add `dist/` via their own
  per-bank `.gitignore`.
- `README.md` — status, requirements, licensing summary.

## Key files on the BaseSkill side (reference only; do not edit from this repo)

- `~/Sites/base-skill/src/data/words/phoneme-audio.ts` — consumer:
  lazy-decodes the MP3 sprite, seeks by `{start, duration}` offsets,
  loops seamlessly when `loopable: true`. No TTS fallback; silent
  no-op on load failure.
- `~/Sites/base-skill/public/audio/phonemes.mp3` +
  `phonemes.json` — the output contract this tool must match.
- `~/Sites/base-skill/scripts/generate-phoneme-sprite.ts` — the
  current eSpeak-NG + ffmpeg build pipeline the recorder is replacing
  (or supplementing) with human voice.

## Next steps

1. [ ] User reviews PR #1. Either merge, or request edits (I push
       fixes to the same branch).
2. [ ] User opens a fresh Claude Code session with `cwd =
       ~/Sites/ipa-phonemes-recorder/`.
3. [ ] Fresh session invokes `superpowers:writing-plans` against the
       spec to produce `docs/plans/2026-MM-DD-initial-implementation.md`
       on a new branch (e.g., `plan/initial-implementation`), opens a
       second PR.
4. [ ] Once plan is approved, execute per the milestone order in spec
       §16: server skeleton → bank listing → mic + record → takes +
       keeper → reference audio → export pipeline → privacy flag +
       per-bank gitignore → new-bank flow + polish.
5. [ ] When a bank is first exported, drop its
       `dist/phonemes.{mp3,json}` into `base-skill/public/audio/` and
       verify playback in BaseSkill's `WordLibraryExplorer` story
       before declaring v1 done.

## Context to remember

- **BaseSkill phoneme format is strict.** Raw Unicode IPA keys,
  22.05 kHz mono MP3 (~56 kbps VBR), manifest shape
  `{ "ipa-char": { "start": ms, "duration": ms, "loopable"?: bool } }`.
  BaseSkill does no schema validation — a mismatch fails silently, so
  golden-file tests on the exporter are worth their weight.
- **User is Leo Caseiro** (senior dev on BaseSkill). Preferences that
  apply here: named exports only (no `export default` except in
  framework configs), PR workflow for every change (no direct master),
  commits freely, pushes features freely, confirms before push only
  for bug fixes, TDD for bug fixes is mandatory.
- **Worktree convention** does **not** apply to this repo — it is a
  BaseSkill-specific rule for the `~/Sites/base-skill` tree. Branches
  are fine here.
- **Child-voice safeguarding** was a specific user concern. The
  privacy flag + per-bank `.gitignore` + UI confirm dialogs encode
  this in §13 of the spec. Do not loosen these defaults without an
  explicit user request.
- **Premium-app context.** User plans to use recordings in a
  closed-source paid app. License strategy accommodates this: user
  owns recordings and can use them privately regardless of public
  license; the public CC-BY-4.0 grant does not constrain user's own
  use.
- **Wikimedia Commons IPA audio** is the primary reference source,
  starting from https://en.wikipedia.org/wiki/IPA_consonant_chart_with_audio
  (and the equivalent vowel chart page). eSpeak-NG is the fallback.
- **Most brainstorming context is not in the new repo** — it lives
  only in the chat log that produced this handoff and in PR #1's
  description. If the fresh session needs more background than the
  spec provides, ask the user.
