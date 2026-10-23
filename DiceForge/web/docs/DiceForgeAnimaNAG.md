### Anima NAG

Normalized Attention Guidance ([NAG](https://chendaryen.github.io/NAG.github.io/)) for Anima: the negative prompt also steers every cross-attention of the model. With a Turbo LoRA (CFG 1) the negative prompt otherwise does nothing; at a higher CFG it adds to it, for things CFG alone leaves in the picture.

1. Put it on the model line, right before KSampler: the loader's (or LoRA Stack's) `model` in, its `model` out to KSampler.
2. Write what you don't want in KSampler's negative prompt, as usual: NAG uses that one, there is no second negative.

| Input | Default | Description |
|---|---|---|
| `model` | | An Anima model (2B, 2.9B, 3.8B; bf16 or compressed), after LoRAs. |
| `nag_scale` | 5 | How far from the negative prompt: 1 is off, about 3–7 a clear push. Higher ones change more of the picture. |
| `nag_alpha` | 0.5 | How much of the guided attention goes in: 0 is off, 1 all of it. |
| `nag_tau` | 1.5 | Under **Advanced**: the most the guidance may grow the attention's size, as a multiple of the positive prompt's. It keeps a high scale from burning the picture. |

| Output | Description |
|---|---|
| `model` | The model with NAG: connect it to KSampler. |

A witch on a hill with `witch hat, hat, headwear` in the negative prompt (Anima base, 896×1152, two seeds, RTX 5060): with the Turbo LoRA at CFG 1 she keeps her hat without NAG and loses it with NAG at the defaults; at CFG 4 she keeps it even with the negative prompt, and loses it with NAG. The pose, the broom and the moon stay.

- In each block, the cross-attention runs once more for the positive prompt, with the negative prompt's text, and the two are blended. The negative is the one ComfyUI already has for CFG, through Anima's own text adapter.
- At CFG above 1 it costs almost nothing (30 steps: 43 s with, 44 s without). At CFG 1 ComfyUI normally skips the negative prompt, so the node turns it back on: 10 Turbo steps took 13–14 s instead of 5 s.
- It needs the positive and negative prompts in the same batch, as ComfyUI runs them unless the VRAM is too low; a step that runs them apart has no NAG.
- ComfyUI's own *Normalized Attention Guidance* node doesn't change Anima: it patches an attention output that Anima doesn't pass through.
- With several Anima NAG nodes in a row, the last one counts. On a model other than Anima it stops with an error that says so.
