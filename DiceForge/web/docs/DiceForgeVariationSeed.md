### Variation Seed

Variations of a picture, as A1111's *variation seed* (subseed): the same composition with small differences. KSampler starts from noise made from its seed; Variation Seed blends that noise with the noise of a second seed, the variation seed (`variation_seed`), by `variation_strength`. The blend is spherical (slerp), so the noise keeps the size the model expects.

1. Put it on the model line, right before KSampler: the loader's (or LoRA Stack's) `model` in, its `model` out to KSampler.
2. Set KSampler's seed to the picture you like and its *control after generate* to *fixed*.
3. Set Variation Seed's *control after generate* to *increment* and queue: every run is another variation. Connect `label` to Dice Grid to see them side by side, and keep the best with ★.

| `variation_strength` | What changes |
|---|---|
| `0` | Nothing: KSampler's seed's own picture. |
| `0.05`–`0.15` | The same pose, composition and character; other folds, strands of hair, background details, expression. |
| `0.2`–`0.4` | Visibly different details; the picture is still recognizable. |
| `1` | The variation seed's own picture. |

- Reproducible: the same seed, variation seed and strength always give the same picture.
- It works with the plain KSampler for every model (SD 1.5, SDXL, Illustrious, NoobAI eps and v-pred, Pony, Flux, Anima…), since it changes the noise the sampling starts from, not the latent: flow models (Flux, Anima, Qwen) don't read the latent at full denoise.
- With several Variation Seed nodes in a row, the last one counts.
- [XY Plot](https://github.com/DeduxOnline/ComfyUI-DiceForge#xy-plot) has `variation seed` and `variation strength` axes: a grid of variations of one picture (with `variation_strength` 0.1 under Advanced), or of strengths.
