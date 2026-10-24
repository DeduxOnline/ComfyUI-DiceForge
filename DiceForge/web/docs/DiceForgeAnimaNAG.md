Normalized Attention Guidance for Anima: the negative prompt also steers every cross-attention. It makes the negative prompt work at CFG 1 (Turbo LoRAs), and strengthens it at a higher CFG. Put it between the model and KSampler.

## Inputs

| Input | Type | Description |
|---|---|---|
| `model` | MODEL | An Anima model (after LoRAs). Connect the output to KSampler's model. |
| `nag_scale` | FLOAT | How far from the negative prompt: 1 is off, about 3-7 a clear push, higher ones can burn the picture. |
| `nag_alpha` | FLOAT | How much of the guided attention goes in: 0 is off, 1 all of it. |

## Advanced inputs

Under **Show advanced inputs** on the node.

| Input | Type | Description |
|---|---|---|
| `nag_tau` | FLOAT | The most the guidance may grow the attention's size (L1 norm), as a multiple of the positive's: keeps a high scale from burning the picture. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `model` | MODEL | The model with NAG: connect it to KSampler. The negative prompt is KSampler's negative. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#anima-nag): examples, tips, and how it works with the other nodes.
