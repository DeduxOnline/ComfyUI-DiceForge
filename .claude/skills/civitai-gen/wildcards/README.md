# Wildcard Registry

Store reusable wildcard lists here. Files are referenced in experiment specs with `@name` shorthand.

## Formats
- `.txt` — One value per line
- `.json` — JSON array (supports named objects with `name`/`value` fields)

## Usage
Reference by short name in experiment specs or CLI:
  --wildcard "color=@neon-colors"
  "wildcards": { "color": "@neon-colors" }

Or by full path:
  --wildcard "style=@/path/to/custom-styles.txt"
