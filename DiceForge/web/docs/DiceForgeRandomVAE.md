Loads a VAE picked from a folder, like Load VAE, with the DiceForge seed modes (deck, shuffle... go through every VAE before repeating one).

![Random LoRA, Random Checkpoint, Random Diffusion Model and Random VAE in Nodes 2.0](images/random_loaders.png)

## Inputs

- `folder` (COMBO, default `(all)`): The folder to pick the VAE from, subfolders included. (all): every VAE. Refresh the node definitions (R) after adding folders.
- `seed` (INT, default `0`): Seed for the random pick. With deck or sequential, set control after generate to increment.

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

- `seed_mode` (COMBO, default `random`): How the pick changes from run to run. random: every pick is independent, so the same one can come up again soon. deck: the seed steps through a shuffled order of the VAEs; with control after generate on increment, every one comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the VAEs already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same pick again. balanced: one just picked gets a low chance, and those not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same pick again. sequential: the seed is the position in the list (sorted by name), so seeds 0, 1, 2... go through the VAEs in order. Reproducible.

## Outputs

- `vae` (VAE): The VAE used for encoding and decoding images to and from latent space.
- `vae_name` (STRING): The picked VAE file, for example for the label of Dice Grid.

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#random-lora-random-checkpoint-random-diffusion-model-and-random-vae): examples, tips, and how it works with the other nodes.
