# Music Generation (ACE Step 1.5)

Generate full songs and music from text descriptions and structured lyrics.

## Quick Start

```bash
# Simple music from text description
node generate.mjs music --prompt "upbeat electronic dance track with synths" -o ./out

# With structured lyrics
node generate.mjs music --prompt "acoustic folk ballad" \
  --lyrics "[verse] Walking through the morning light..." \
  --duration 30 -o ./out

# With specific model
node generate.mjs music --prompt "lo-fi hip hop beat" \
  --model "urn:air:..." --duration 60 -o ./out
```

## Parameters

| Flag | Required | Description |
|------|----------|-------------|
| `--prompt <text>` | yes | Text description of the music to generate |
| `--lyrics <text>` | no | Structured lyrics for the song (use `[verse]`, `[chorus]` tags) |
| `--duration <sec>` | no | Duration in seconds |
| `--model <air>` | no | Model identifier in AIR format |

## Output

Music outputs a single `.mp3` file per step. The JSON summary includes an `audio` array with paths.

## Notes

- Use descriptive prompts: genre, instruments, tempo, mood
- Structured lyrics use tags like `[verse]`, `[chorus]`, `[bridge]` to guide song structure
- Duration controls the length of the generated audio
