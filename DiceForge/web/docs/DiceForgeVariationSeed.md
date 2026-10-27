Variations of a picture, as A1111's variation seed: the noise of KSampler's seed is blended with the noise of the variation seed. A low strength keeps the composition and changes details. Put it between the model and KSampler.

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `model` | MODEL |  | The model (after LoRAs). Connect the output to KSampler's model. |
| `variation_seed` | INT | `0` | The second seed. With control after generate on increment, every run is another variation of the same picture (KSampler's seed fixed). |
| `variation_strength` | FLOAT | `0.1` | How much of the variation seed's noise: 0 is KSampler's seed's own picture, 0.05-0.15 the same composition with other details, 0.3 visibly different, 1 the variation seed's own picture. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `model` | MODEL | The model whose sampling starts from the blended noise: connect it to KSampler. |
| `label` | STRING | For Dice Grid's label: the variation seed and strength. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#variation-seed): examples, tips, and how it works with the other nodes.
