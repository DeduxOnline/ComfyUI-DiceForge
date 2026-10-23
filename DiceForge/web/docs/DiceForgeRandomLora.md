### Random LoRA, Random Checkpoint, Random Diffusion Model and Random VAE

![Random LoRA, Random Checkpoint, Random Diffusion Model and Random VAE in Nodes 2.0](images/random_loaders.png)

Loaders that pick the file from a folder with the [seed modes](https://github.com/DeduxOnline/ComfyUI-DiceForge#seed-modes-for-sizes), then load it with the core loader (**Load LoRA**, **Load Checkpoint**, **Load Diffusion Model**, **Load VAE**), so the result is the same as picking that file by hand.

| Input | Where | Description |
|---|---|---|
| `folder` | main | A folder in `models/loras`, `models/checkpoints`, `models/diffusion_models` or `models/vae`, subfolders included; `(all)` for every file. After adding folders, refresh the node definitions (**R**). |
| `seed` | main | Seed for the pick. With `deck` or `sequential`, set *control after generate* to *increment*. |
| `seed_mode` | Advanced | `random`, `deck`, `shuffle`, `balanced` or `sequential`, as for the resolution nodes. `sequential` goes through the files sorted by name. |
| `model`, `clip` | Random LoRA | The model and CLIP to apply the LoRA to. `clip` is optional: leave it unconnected to change only the model. |
| `strength_model`, `strength_clip` | Random LoRA | As in **Load LoRA**. Connect **Random Float** to them to vary the strength too. |
| `include_none` | Random LoRA, Advanced | Adds "no LoRA" as one more option, so some runs use the model as it is. |
| `weight_dtype` | Random Diffusion Model, Advanced | As in **Load Diffusion Model**. |

Each loader outputs what its core loader does (`model`, `clip`, `vae`) plus the picked file name (`lora_name`, `ckpt_name`, `model_name`, `vae_name`; empty for "no LoRA"), for example to put it in the image file name. The picked file is also written to the console.

- Adding or removing files in the folder makes the node pick again, and `deck`, `shuffle` and `balanced` start a new round for the new list.
- An empty folder stops the run with an error that names it.
- With `deck` and *increment*, a checkpoint comparison shows every checkpoint once before any repeats; with `shuffle` it continues after a restart.
