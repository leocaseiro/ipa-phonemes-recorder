# ipa-phonemes-recorder

A local-only desktop tool for recording IPA phoneme sounds with your own
voice, producing drop-in soundfont bundles for phonics apps such as
[BaseSkill](https://github.com/leocaseiro/base-skill).

## Status

**Early design.** The design spec lives under
[docs/specs/](./docs/specs/). Implementation has not started.

## What it does

- Presents an extensible list of IPA phonemes grouped into **banks** (one
  bank = one language / accent / speaker combination).
- Records multiple takes per phoneme through a browser UI backed by a
  Python stdlib HTTP server.
- Plays a **reference** clip (Wikimedia Commons IPA audio, with
  eSpeak-NG fallback) so the speaker can hear the target sound.
- Exports a BaseSkill-compatible MP3 sprite plus JSON manifest
  (`phonemes.mp3` + `phonemes.json`).

## Requirements

- Python 3.10+ (stdlib only — no pip, no venv).
- `ffmpeg` and `espeak-ng` on `PATH`.
- A reasonable microphone.
- macOS, Linux, or Windows. Primary target: macOS.

## Licensing

- **Code:** MPL-2.0 — see [LICENSE](./LICENSE).
- **Public bank recordings (when committed):** CC-BY-4.0. Attribution
  string is declared per bank in that bank's `config.json`.
- **Private bank recordings:** stay local, never committed. The tool
  writes a per-bank `.gitignore` to enforce this.

## Children's voices

By default, every new bank is created with `privacy: "private"`. Voice
is biometric data; Creative Commons licensing is effectively
irrevocable once published. Keep children's banks private unless you
have explicit, informed, long-term consent from the speaker.
