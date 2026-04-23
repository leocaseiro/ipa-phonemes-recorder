# Claude Code Rules for ipa-phonemes-recorder

A local tool for recording IPA phoneme sounds and producing soundfont
bundles compatible with the
[BaseSkill](https://github.com/leocaseiro/base-skill) phonics app.

## Status

Early design phase. The validated design spec lives at
[`docs/specs/`](./docs/specs/). Implementation has not started.

## Git workflow

- `master` is protected. No direct commits.
- Every change lands through a branch and a pull request.
- Branch names follow `docs/<topic>`, `feat/<topic>`, `fix/<topic>`,
  `chore/<topic>`.
- Commit messages follow Conventional Commits where practical
  (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).
- Small, focused commits are preferred over giant ones.

## Tech stack rules

- **Python 3.10+, stdlib only.** No pip, no venv, no `requirements.txt`.
- **UI** is plain HTML + vanilla JS. No build step, no bundler, no
  framework.
- **Audio tooling** (`ffmpeg`, `espeak-ng`) is invoked via subprocess.
  Both must be on `PATH`.

## License

- **Code:** MPL-2.0. Every new Python/JS/HTML/CSS source file added to
  the repo should start with the MPL-2.0 file-header notice (see
  [LICENSE](./LICENSE) Exhibit A).
- **Public bank recordings:** CC-BY-4.0. The attribution string is
  declared per bank in that bank's `config.json`.
- **Private bank recordings:** stay on the user's machine. Enforced by
  a per-bank `.gitignore` the tool writes on bank creation.

## Test-driven development

For any bug fix: write a failing test first, confirm it reproduces the
bug, then apply the minimal fix. Do not open a bug-fix PR without a
regression test.

For new features: write tests as part of the implementation, not after.

## Safety: children's voices

When touching the privacy-flag handling or any gitignore logic, be
paranoid about preventing accidental publication of children's
recordings.

- Default every new bank to `privacy: "private"`.
- Never flip a bank public without explicit user confirmation.
- Reference audio is strictly read-only from the export pipeline.
- Before committing any new bank, verify its `.gitignore` matches the
  bank's declared `privacy` field.

## Markdown

Plain Markdown. Keep it readable. No repo-wide linter is configured
(yet). Prefer `-` for unordered lists, fenced code blocks, and
reference-style links for long URLs.
