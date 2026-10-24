As Easy-Use's HiresFix, with the VAE from a list: the image made bigger with an upscale model, rescaled, shown or saved, and encoded into a latent for a second KSampler pass.

## Inputs

| Input | Type | Description |
|---|---|---|
| `image` | IMAGE | The image of the first pass (VAE Decode, or VAE Decode + Save's images). |
| `model_name` | COMBO | The upscale model (models/upscale\_models: ESRGAN, 4x-UltraSharp, AnimeSharp...). None: only rescaled. |
| `rescale_after_model` | BOOLEAN | Rescale the upscaled image (below). Off: keep the upscale model's size (4x for a 4x model). |
| `rescale_method` | COMBO | How the image is resized after the model. |
| `rescale` | COMFY_DYNAMICCOMBO_V3 | The size after the upscale model: by percentage, to a width and/or height, or to a longest side. Rounded to multiples of 8 for the latent. |
| `crop` | COMBO | With an exact width and height of another aspect ratio: disabled stretches, center crops. |
| `vae_name` | COMBO | The VAE that encodes the image into the latent. Same list as Load VAE. |
| `image_output` | COMBO | Hide: only pass the image on. Preview: show it on the node. Save: save and show it, like Save Image. Hide&Save: save without showing. |

## Advanced inputs

Under **Show advanced inputs** on the node.

| Input | Type | Description |
|---|---|---|
| `filename_prefix` | STRING | The prefix for the file to save. A / makes a subfolder. May include %year%, %month%, %day%, %hour%, %minute%, %second%, %width% and %height%. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `image` | IMAGE | The upscaled and rescaled image. |
| `latent` | LATENT | The image encoded with the VAE: for a second KSampler pass (denoise 0.3-0.5). |
| `vae` | VAE | The VAE used for decoding, passed on: for example for VAE Encode in a hires fix or inpaint. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#hiresfix-load-vae): examples, tips, and how it works with the other nodes.
