### XY Plot

An X/Y comparison in one node. Each run gives **KSampler** the settings of one cell and **Dice Grid** its labels; **▶ Queue** on the node queues a run for every cell.

How to connect it:

1. Connect `seed`, `steps`, `cfg`, `sampler_name`, `scheduler` and `denoise` to KSampler (drag each onto KSampler's field of the same name). For a LoRA axis, put XY Plot between the loader and KSampler: `model` and `clip` in, `model` and `clip` out (to KSampler and the prompt encoder).
2. Connect `x_label` to Dice Grid's `label`, `y_label` to `row_label`, and `count`, `columns` and `new_grid` to the Dice Grid fields of the same name. Dice Grid then starts a fresh grid on the first cell, and saves it after the last one with the values as column and row headers.
3. Pick what changes on X and on Y (`x_type`, `y_type`) and type the values (`x_values`, `y_values`). The node shows the headers and the number of images; click **▶ Queue N images** (click again to stop queueing).

| Axis | Values | Example |
|---|---|---|
| `seed`, `steps` | Whole numbers and ranges | `1, 2, 3` · `20-40:10` |
| `cfg`, `lora strength`, `denoise` | Numbers and ranges `start-end:step` (step 1 unless given) | `4, 5.5, 7` · `3.5-7:0.5` · `-1..1:0.5` |
| `sampler`, `scheduler` | Names from KSampler's lists, `*` for all | `euler, dpmpp_2m` |
| `lora` | LoRA files, with or without folder and extension; patterns; `None` for the image without a LoRA | `style/*, None` · `ink` |
| `variation seed`, `variation strength` | As [Variation Seed](https://github.com/DeduxOnline/ComfyUI-DiceForge#variation-seed): seeds (`1-8`), strengths (`0-0.3:0.05`); the other one is set under **Advanced** (`variation_strength` 0.1 for a seed axis). Needs `model` connected, its output to KSampler. | `1-8` · `0, 0.05, 0.1, 0.2` |
| `none` | Nothing changes (Y `none`: one row of images) | |

- The other settings (`seed`, `steps`, `cfg`, `sampler_name`, `scheduler`, and under **Advanced** `denoise`, `lora_name`, `lora_strength`, `variation_seed`, `variation_strength`) are used for every cell, except the ones on an axis. With a `lora strength` axis, `lora_name` is the LoRA it changes.
- `index` is the cell of a run, row by row. **▶ Queue** sets it for each run and puts it back to 0; Run alone makes the cell at `index`.
- Up to 64 values per axis and 256 images in all. A field the node can't read is shown in red under it, and stops the run with the same message.
- Connect `seed` to KSampler, or set KSampler's own *control after generate* to *fixed*: otherwise every cell gets another seed. XY Plot's `seed` has no *control after generate*, so it stays the same from cell to cell.
