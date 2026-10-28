As Easy-Use's HiresFix, with the VAE from a list: the image made bigger with an upscale model, rescaled, shown or saved, and encoded into a latent for a second KSampler pass.

## Inputs

- `image` (IMAGE): The image of the first pass (VAE Decode, or VAE Decode + Save's images).
- `model_name` (COMBO): The upscale model (models/upscale\_models: ESRGAN, 4x-UltraSharp, AnimeSharp...). None: only rescaled.
- `rescale_after_model` (BOOLEAN, default on): Rescale the upscaled image (below). Off: keep the upscale model's size (4x for a 4x model).
- `rescale_method` (COMBO, default `lanczos`): How the image is resized after the model.
- `rescale` (COMBO): The size after the upscale model: by percentage, to a width and/or height, or to a longest side. Rounded to multiples of 8 for the latent.
  - `percent` (INT, default `50`, for by percentage): Each side in percent of the image after the upscale model (of the image as it came without one): a 4x model at 50% gives twice the size.
  - `width` (INT, default `1536`, for to Width/Height): The width. 0: follows the aspect ratio from the height.
  - `height` (INT, default `0`, for to Width/Height): The height. 0: follows the aspect ratio from the width. Both set: that exact size (crop decides what happens to a different aspect ratio).
  - `longer_side` (INT, default `2048`, for to longest side): The longest side, keeping the aspect ratio.
- `crop` (COMBO, default `disabled`): With an exact width and height of another aspect ratio: disabled stretches, center crops.
- `vae_name` (COMBO): The VAE that encodes the image into the latent. Same list as Load VAE.
- `image_output` (COMBO, default `Preview`): Hide: only pass the image on. Preview: show it on the node. Save: save and show it, like Save Image. Hide&Save: save without showing.

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

- `filename_prefix` (STRING, default `DiceForge/hires`): The prefix for the file to save. A / makes a subfolder. May include %year%, %month%, %day%, %hour%, %minute%, %second%, %width% and %height%.

## Outputs

- `image` (IMAGE): The upscaled and rescaled image.
- `latent` (LATENT): The image encoded with the VAE: for a second KSampler pass (denoise 0.3-0.5).
- `vae` (VAE): The VAE loaded: for the VAE Decode after the second KSampler.

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#hiresfix-load-vae): examples, tips, and how it works with the other nodes.
