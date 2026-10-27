Loads a diffusion model (like Load Diffusion Model) and its text encoders (like Load CLIP, or DualCLIPLoader when clip\_name2 is set) in one node.

![VAE Decode + Save, Load VAE + Decode + Save and Load Diffusion Model + CLIP in Nodes 2.0](images/utility_nodes.png)

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `unet_name` | COMBO |  | The diffusion model to load, from models/diffusion\_models. |
| `clip_name1` | COMBO |  | The text encoder to load, from models/text\_encoders. |

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

| Input | Type | Default | Description |
|---|---|---|---|
| `clip_name2` | COMBO |  | The second text encoder. None loads only clip\_name1, like Load CLIP. A file loads both, like DualCLIPLoader. |
| `type` | COMBO | `stable_diffusion` | The model the text encoders are for. Some types need one file, some need two. |
| `weight_dtype` | COMBO | `default` | Weight precision of the diffusion model, as in Load Diffusion Model. |
| `device` | COMBO | `default` | Where the text encoders run, as in Load CLIP. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `model` | MODEL | The diffusion model. |
| `clip` | CLIP | The text encoders. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#utility-nodes): examples, tips, and how it works with the other nodes.
