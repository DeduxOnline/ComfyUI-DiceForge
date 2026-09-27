# Text-to-Speech (TTS)

Synthesize speech from text using Civitai's orchestration API. Two modes: built-in speakers (CustomVoice) or voice cloning from reference audio (Base).

## Quick Start

```bash
# Built-in speaker
node generate.mjs tts --text "Hello world" --speaker serena -o ./out

# With style instruction
node generate.mjs tts --text "Welcome to Civitai" --speaker dylan \
  --instruct "cheerful and enthusiastic" -o ./out

# Voice cloning from reference audio
node generate.mjs tts --text "Cloned speech" --ref-audio "https://example.com/voice.wav" -o ./out

# Voice cloning with transcript (improves quality)
node generate.mjs tts --text "Cloned speech" \
  --ref-audio "urn:air:other:other:orchestrator:blob@sample.wav" \
  --ref-text "This is the transcript of the reference audio" -o ./out

# Speaker embedding only (no reference transcript needed)
node generate.mjs tts --text "Using embedding" --ref-audio "https://..." --x-vector-only -o ./out
```

## Parameters

### CustomVoice Mode (built-in speakers)

| Flag | Required | Description |
|------|----------|-------------|
| `--text <text>` | yes | Text to synthesize |
| `--speaker <name>` | yes | Built-in speaker: aiden, dylan, eric, ono_anna, ryan, serena, sohee, uncle_fu, vivian |
| `--language <lang>` | no | Language (default: "English") |
| `--instruct <text>` | no | Style/tone instruction (e.g. "cheerful and enthusiastic", "whisper softly") |

### Base Mode (voice cloning)

| Flag | Required | Description |
|------|----------|-------------|
| `--text <text>` | yes | Text to synthesize |
| `--ref-audio <url>` | yes | URL or AIR URN of reference audio file |
| `--ref-text <text>` | no | Transcript of the reference audio (improves cloning quality) |
| `--x-vector-only` | no | Use speaker embedding only — no reference transcript needed |
| `--language <lang>` | no | Language (default: "English") |

## Output

TTS outputs a single `.ogg` file per step. The JSON summary includes an `audio` array with paths to downloaded files.

## Notes

- The mode is auto-detected: if `--ref-audio` is provided, Base (voice cloning) mode is used; otherwise CustomVoice mode requires `--speaker`.
- Style instructions (`--instruct`) only work in CustomVoice mode.
- Reference audio should be a clean recording of the target voice (ideally 5-30 seconds).
- AIR URN format for blobs: `urn:air:other:other:orchestrator:blob@filename.wav`
