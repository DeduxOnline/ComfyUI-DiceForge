VAE Decode and Save Image in one node: decodes the latent with the VAE of its vae input, then shows or saves the images as image\_output says.

![VAE Decode + Save, Load VAE + Decode + Save and Load Diffusion Model + CLIP in Nodes 2.0](images/utility_nodes.png)

## Inputs

| Input | Type | Description |
|---|---|---|
| `samples` | LATENT | The latent to decode. |
| `vae` | VAE | The VAE used for decoding, for example the VAE output of Load Checkpoint or Load VAE. |
| `filename_prefix` | STRING | The prefix for the file to save. A / makes a subfolder. May include %year%, %month%, %day%, %hour%, %minute%, %second%, %width% and %height%. |
| `image_output` (optional) | COMBO | Hide: only pass the images on. Preview: show them on the node without saving. Save: save the PNG files and show them, like Save Image. Hide&Save: save without showing. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `images` | IMAGE | The decoded images, passed on whatever image\_output is: for example to an upscale. |
| `vae` | VAE | The VAE used for decoding, passed on: for example for VAE Encode in a hires fix or inpaint. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#utility-nodes): examples, tips, and how it works with the other nodes.
