Normalized Attention Guidance for Anima: the negative prompt also steers every cross-attention. It makes the negative prompt work at CFG 1 (Turbo LoRAs), and strengthens it at a higher CFG. Put it between the model and KSampler.

At CFG 1 ComfyUI skips the negative prompt, so the node turns it back on: 10 Turbo steps take 13–14 s instead of 5 s. It needs the positive and negative prompts in one batch: when low VRAM makes ComfyUI run them apart, that step has no NAG. With several Anima NAG nodes in a row, the last one counts; on a model other than Anima it stops with an error.

## Inputs

- `model` (MODEL): An Anima model (after LoRAs). Connect the output to KSampler's model.
- `nag_scale` (FLOAT, default `5`): How far from the negative prompt: 1 is off, about 3-7 a clear push, higher ones can burn the picture.
- `nag_alpha` (FLOAT, default `0.5`): How much of the guided attention goes in: 0 is off, 1 all of it.

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

- `nag_tau` (FLOAT, default `1.5`): The most the guidance may grow the attention's size (L1 norm), as a multiple of the positive's: keeps a high scale from burning the picture.

## Outputs

- `model` (MODEL): The model with NAG: connect it to KSampler. The negative prompt is KSampler's negative.

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#anima-nag): examples, tips, and how it works with the other nodes.
