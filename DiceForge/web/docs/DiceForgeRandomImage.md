### Random Image

![Random Image in deck mode feeding Dice Grid, after four runs](images/random_image_dice_grid.png)

Like **Load Image**, but the image is picked from a folder with the [seed modes](https://github.com/DeduxOnline/ComfyUI-DiceForge#seed-modes-for-sizes): with `deck` and *increment* an img2img or ControlNet series goes through every image once before any repeats. After each run the node shows the picked image, its file name (click to copy), size (and frames of an animated one), folder, and the seed and mode it came from; click the image to open it full size. The preview is kept with the workflow, so it is still there after a reload, and it also updates when the node comes from ComfyUI's cache. A file of the input folder is shown from there; one from `path` through a temporary copy, which ComfyUI clears on restart (the preview then says to run again).

| Input | Where | Description |
|---|---|---|
| `folder` | main | A folder in `ComfyUI/input`, subfolders included; `(all)` for every image in `input` (the mask editor's `clipspace` folder is left out). After adding folders, refresh the node definitions (**R**). |
| `seed` | main | Seed for the pick. With `deck` or `sequential`, set *control after generate* to *increment*. |
| `seed_mode` | Advanced | `random`, `deck`, `shuffle`, `balanced` or `sequential` (files sorted by name). |
| `path` | Advanced | Any folder on this computer instead, for example `D:/refs/poses` (subfolders included). Empty: use `folder`. |

| Output | Description |
|---|---|
| `image` | The picked image; all frames for an animated GIF or WebP, as in Load Image. |
| `mask` | The mask from the alpha channel (1 where transparent), as in Load Image. |
| `file_name` | The picked file, relative to the folder. |

- Supported files: png, jpg, jpeg, webp, bmp, gif, tif, tiff.
- The image is loaded with the same steps as Load Image, and gives the same result. When ComfyUI's video reader fails on a file (it does on some WebP files, and then Load Image fails too), Random Image reads it with Pillow instead.
- Adding, removing or editing images in the folder makes the node pick again.
