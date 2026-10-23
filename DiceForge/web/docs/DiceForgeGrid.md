### Dice Grid

Collects the image of each run into a grid with labels, and saves the grid to the output folder when it is finished. Made for DiceForge series: connect the `lora_name`, `ckpt_name` or `file_name` output of a random loader to `label`, set the loader to `deck` with *increment*, and queue: after one round the grid holds every file once, with its name under it.

| Input | Where | Default | Description |
|---|---|---|---|
| `image` | main | | The image of this run. Every image of a batch (or frame of an animation) becomes a cell. |
| `label` | input | | Caption of the image. Model and image file names are shown without folder and extension (`anime/ink.safetensors` → `ink`). In an XY grid, the column. |
| `row_label` | input | | Connect it to make an XY grid: rows by `row_label`, columns by `label`, with headers. For example checkpoint × LoRA with `combinations`, or two loaders in `sequential`. |
| `count` | main | `0` | Images in a finished grid. `0`: the grid is finished when a label (or label pair) comes again, which is the end of a `deck` or `shuffle` round. |
| `columns` | main | `0` | Images per row; `0` makes the grid about square. XY grids take their columns from the labels. |
| `save` | main | on | Save each finished grid as a PNG in the output folder, with the workflow in it like **Save Image**. |
| `legend` | main | | Text in a block above or below the grid: a title, the settings that stay the same, or the prompt (connect `positive_text` of **CLIP Dual Text Encode**, which shows the prompt each grid was made with). |
| `numbered` | main | off | Numbers the images and lists their full labels in the legend (`1. very_long_style_name_v2`), for labels too long to fit under an image. XY grids keep their headers instead. |
| `cell_width` | Advanced | `384` | Width of each cell. Heights follow the aspect ratio, so images of different sizes (from the random resolution nodes) fit side by side. |
| `filename_prefix` | Advanced | `DiceForge/grid` | File name prefix of saved grids. |
| `name` | Advanced | `grid` | Grids are kept per node and name; another name starts a separate grid. |
| `new_grid` | Advanced | off | Starts a new grid with this image, dropping the unfinished one. Turn it off again for the next runs. |
| `legend_position` | Advanced | `top` | Where the legend goes: `top` or `bottom`. |

| Output | Description |
|---|---|
| `grid` | The grid so far, this run's image included (also shown on the node). |
| `cells` | Images in the grid so far. |

#### Keeping the best images

Under the node, the cells of the grid being made (or of the last finished one, until the next run starts a new grid) are shown small:

- Click a cell to star it (★); click again to unstar it.
- **💾 Save N kept** saves the starred ones at full size in `output/DiceForge/kept` (`kept_00001_<row>_<label>.png`), each with the workflow and prompt of its own run in it, like **Save Image**.
- **↺** on a cell opens, after asking, the workflow of its run (its prompts and seeds included), as dropping its image on ComfyUI would: to make it again, or go on from it with HiresFix (Load VAE).

- The cells wait between runs as small PNG files in `ComfyUI/user/DiceForge/grids`, not in RAM, so an unfinished grid survives a restart. Next to each is the image at full size with its run's workflow, for keeping; they go when the next grid starts.
- The node adds a cell on every run, even if nothing else changed, so queueing the same image twice adds it twice (and, with `count` 0 and a label, finishes the grid).
