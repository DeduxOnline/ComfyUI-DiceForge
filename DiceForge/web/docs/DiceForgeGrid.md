Collects the image of each run into a labeled grid (a comparison of LoRAs, checkpoints, samplers...) and saves it when it is finished.

## Inputs

| Input | Type | Description |
|---|---|---|
| `image` | IMAGE | The image of this run. Each run adds it to the grid (every image of a batch). |
| `label` (optional) | STRING | Caption of the image, for example lora\_name or ckpt\_name from a random loader. File names are shown without folder and extension. In an XY grid: the column. |
| `row_label` (optional) | STRING | Connect to make an XY grid: rows by this label, columns by label (for example checkpoint x LoRA with seed mode combinations). |
| `count` | INT | Images in a finished grid. 0: the grid is finished when a label comes again, which is the end of a round with deck or shuffle. |
| `columns` | INT | Images per row (0: about square). XY grids take their columns from the labels. |
| `save` | BOOLEAN | Save each finished grid to the output folder. |
| `legend` | STRING | Text shown in a block above or below the grid: a title, the settings that stay the same, or the prompt (connect positive\_text of CLIP Dual Text Encode). |
| `numbered` | BOOLEAN | Number the images and list their full labels in the legend (1. anime/ink ...), for labels too long to fit under an image. Not for XY grids, which have headers. |

## Advanced inputs

Under **Show advanced inputs** on the node.

| Input | Type | Description |
|---|---|---|
| `cell_width` | INT | Width of each image in the grid; heights follow the aspect ratio, so images of different sizes fit. |
| `filename_prefix` | STRING | File name prefix of saved grids, in the output folder. |
| `name` | STRING | Grids are kept per node and name: another name starts a separate grid (the old one stays until you come back to its name). |
| `new_grid` | BOOLEAN | Start a new grid with this image (the unfinished one is dropped). Turn it off again for the next runs. |
| `legend_position` | COMBO | Where the legend goes: above or below the grid. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `grid` | IMAGE | The grid so far, this run's image included. |
| `cells` | INT | Images in the grid so far. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#dice-grid): examples, tips, and how it works with the other nodes.
