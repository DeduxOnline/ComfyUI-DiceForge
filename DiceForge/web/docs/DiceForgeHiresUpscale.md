### HiresFix (Load VAE)

Like Easy-Use's *HiresFix*, with the VAE picked from a list instead of a `vae` input: the image of the first pass is made bigger with an upscale model, rescaled, shown or saved, and encoded into a latent for a second KSampler pass (denoise 0.3–0.5). It prepares the image and the latent for your own KSampler.

| Input | Default | Description |
|---|---|---|
| `image` | | The image of the first pass (VAE Decode, or VAE Decode + Save's `images`). |
| `model_name` | the first model | An upscale model from `models/upscale_models` (ESRGAN, 4x-UltraSharp, AnimeSharp…), or `None` to only rescale; kept loaded while the name stays the same. |
| `rescale_after_model` | on | Rescale the upscaled image (below); off keeps the model's size (4× for a 4x model). Without a model the image is always rescaled. |
| `rescale_method` | `lanczos` | How the image is resized: `nearest-exact`, `bilinear`, `area`, `bicubic`, `lanczos`. |
| `rescale` | `by percentage` 50 | Of the image after the model: `percent` (a 4x model at 50% gives twice the size), `to Width/Height` (one of them keeps the aspect ratio), or `to longest side` (`longer_side`, 2048). Rounded to multiples of 8 for the latent. |
| `crop` | `disabled` | With an exact width and height of another aspect ratio: `disabled` stretches, `center` crops. |
| `vae_name` | | The VAE that encodes the image, from the same list as Load VAE; kept loaded while the name stays the same. |
| `image_output` | `Preview` | `Hide`, `Preview`, `Save` or `Hide&Save`, as in Easy-Use. |
| `filename_prefix` | `DiceForge/hires` | Advanced: where `Save` puts the image. |

Outputs: `image` (upscaled and rescaled), `latent` (encoded with the VAE: connect it to a KSampler with denoise 0.3–0.5) and `vae` (for that KSampler's VAE Decode).
