# Transcription / Speech-to-Text (STT)

Transcribe audio/video files to text using automatic speech recognition (ASR).

## Quick Start

```bash
# From a local file (auto-uploads to blob)
node generate.mjs stt recording.mp3 -o ./out

# From a URL
node generate.mjs transcribe --media-url "https://example.com/audio.mp3" -o ./out

# Record from microphone (10 seconds)
node generate.mjs stt --mic 10 -o ./out

# WAV files are auto-converted to MP3 before upload
node generate.mjs stt interview.wav -o ./out

# With language hint and context
node generate.mjs stt recording.mp3 \
  --language en --context "Technical podcast about machine learning" -o ./out

# With word-level timestamps
node generate.mjs stt recording.mp3 --timestamps -o ./out
```

## Parameters

| Flag | Required | Description |
|------|----------|-------------|
| positional arg | no | Local audio file path (auto-uploaded) |
| `--media-file <path>` | no | Local audio file path (explicit flag) |
| `--media-url <url>` | no | URL or AIR URN of the audio/media file |
| `--mic <seconds>` | no | Record from microphone first (default: 10s) |
| `--language <lang>` | no | Language hint (e.g. "en") — improves accuracy |
| `--context <text>` | no | Context about the audio (e.g. "Technical podcast about AI") |
| `--timestamps` | no | Return word-level timestamps |

One of `positional arg`, `--media-file`, `--media-url`, or `--mic` is required.

## Commands

Both `transcribe` and `stt` work as command aliases.

## Output

Transcription does not produce downloadable files. Instead, the JSON summary includes a `transcriptions` array:

```json
{
  "transcriptions": [
    {
      "stepIndex": 0,
      "text": "The full transcribed text...",
      "segments": [
        { "text": "The", "start": 0.0, "end": 0.2 },
        { "text": "full", "start": 0.2, "end": 0.5 }
      ]
    }
  ]
}
```

Segments with timestamps are only included when `--timestamps` is used.

## Notes

- Supports MP3, OGG, FLAC formats directly. WAV files are auto-converted to MP3.
- Language hint is optional but improves accuracy for non-English content
- Context helps the model with domain-specific vocabulary
- Mic recording requires ffmpeg with dshow (Windows), avfoundation (macOS), or alsa (Linux)
- Cost: 1 buzz per transcription
