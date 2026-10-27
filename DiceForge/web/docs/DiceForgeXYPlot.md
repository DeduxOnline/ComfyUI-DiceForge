Settings for an X/Y comparison grid: each run gives KSampler the values of one cell and Dice Grid its labels; ▶ Queue on the node queues every cell.

The node shows the headers and the number of images; **▶ Queue N images** queues a run for every cell (click again to stop). Connect `seed` to KSampler, or set KSampler's *control after generate* to *fixed*: otherwise every cell gets another seed.

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `x_type` | COMBO | `cfg` | What changes from column to column. |
| `x_values` | STRING | `4, 5.5, 7` | Values, separated by commas or new lines. Numbers: 4, 5.5, 7 or ranges 4-8 (step 1) and 3.5-7:0.5. Sampler, scheduler: names, \* for all. LoRA: file names, with or without folder and extension, patterns like style/\*, None for no LoRA. |
| `y_type` | COMBO | `sampler` | What changes from row to row (none: one row). |
| `y_values` | STRING | `euler, euler_ancestral,…` | Values, separated by commas or new lines. Numbers: 4, 5.5, 7 or ranges 4-8 (step 1) and 3.5-7:0.5. Sampler, scheduler: names, \* for all. LoRA: file names, with or without folder and extension, patterns like style/\*, None for no LoRA. |
| `index` | INT | `0` | The cell of this run, row by row (▶ Queue sets it for each run). |
| `seed` | INT | `0` | Seed of every cell, unless an axis is seed. It stays the same from cell to cell. |
| `steps` | INT | `28` | Steps of every cell, unless an axis is steps. |
| `cfg` | FLOAT | `6` | CFG of every cell, unless an axis is cfg. |
| `sampler_name` | COMBO | `euler_ancestral` | Sampler of every cell, unless an axis is sampler. |
| `scheduler` | COMBO | `normal` | Scheduler of every cell, unless an axis is scheduler. |
| `model` (optional) | MODEL |  | The model, for a LoRA (lora\_name, or a lora axis). Passed through otherwise. |
| `clip` (optional) | CLIP |  | The CLIP, for a LoRA. Passed through otherwise. |

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

| Input | Type | Default | Description |
|---|---|---|---|
| `denoise` | FLOAT | `1` | Denoise of every cell, unless an axis is denoise. |
| `lora_name` | COMBO | `None` | LoRA of every cell (for a lora strength axis), unless an axis is lora. Applied to model and clip. |
| `lora_strength` | FLOAT | `1` | LoRA strength, unless an axis is lora strength. |
| `variation_seed` | INT | `0` | Variation seed of every cell (as Variation Seed), unless an axis is variation seed. |
| `variation_strength` | FLOAT | `0` | Variation strength of every cell (0: none). A variation seed axis with strength 0.1: variations of one picture. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `model` | MODEL | The model, with this cell's LoRA. |
| `clip` | CLIP | The CLIP, with this cell's LoRA. |
| `seed` | INT | For KSampler's seed. |
| `steps` | INT | For KSampler's steps. |
| `cfg` | FLOAT | For KSampler's cfg. |
| `sampler_name` | COMBO | For KSampler's sampler\_name. |
| `scheduler` | COMBO | For KSampler's scheduler. |
| `denoise` | FLOAT | For KSampler's denoise. |
| `x_label` | STRING | For Dice Grid's label: the column. |
| `y_label` | STRING | For Dice Grid's row\_label: the row. |
| `count` | INT | Images in the grid, for Dice Grid's count. |
| `columns` | INT | Values on X, for Dice Grid's columns (one row per Y value). |
| `new_grid` | BOOLEAN | True for the first cell, for Dice Grid's new\_grid: each plot starts a fresh grid. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#xy-plot): examples, tips, and how it works with the other nodes.
