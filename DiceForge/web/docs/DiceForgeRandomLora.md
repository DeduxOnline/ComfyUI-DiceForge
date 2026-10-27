Applies a LoRA picked from a folder, like Load LoRA, with the DiceForge seed modes (deck, shuffle... go through every LoRA before repeating one).

![Random LoRA, Random Checkpoint, Random Diffusion Model and Random VAE in Nodes 2.0](images/random_loaders.png)

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `model` | MODEL |  | The diffusion model the LoRA is applied to. |
| `clip` (optional) | CLIP |  | The CLIP model the LoRA is applied to. Leave it unconnected to change only the model. |
| `folder` | COMBO | `(all)` | The folder to pick the LoRA from, subfolders included. (all): every LoRA. Refresh the node definitions (R) after adding folders. |
| `strength_model` | FLOAT | `1` | How strongly to modify the diffusion model. This value can be negative. |
| `strength_clip` | FLOAT | `1` | How strongly to modify the CLIP model. This value can be negative. |
| `seed` | INT | `0` | Seed for the random pick. With deck or sequential, set control after generate to increment. |

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

| Input | Type | Default | Description |
|---|---|---|---|
| `seed_mode` | COMBO | `random` | How the pick changes from run to run. random: every pick is independent, so the same one can come up again soon. deck: the seed steps through a shuffled order of the LoRAs; with control after generate on increment, every one comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the LoRAs already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same pick again. balanced: one just picked gets a low chance, and those not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same pick again. sequential: the seed is the position in the list (sorted by name), so seeds 0, 1, 2... go through the LoRAs in order. Reproducible. |
| `include_none` | BOOLEAN | off | Add "no LoRA" as one more option, so some runs use the model without a LoRA. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `model` | MODEL | The model with the LoRA applied. |
| `clip` | CLIP | The CLIP with the LoRA applied (unconnected CLIP input: nothing). |
| `lora_name` | STRING | The picked LoRA file, for example for the file name of the image. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#random-lora-random-checkpoint-random-diffusion-model-and-random-vae): examples, tips, and how it works with the other nodes.
