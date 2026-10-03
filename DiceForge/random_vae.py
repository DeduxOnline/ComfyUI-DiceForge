import logging
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .model_lists import folder_fingerprint, folder_input, pick_model_file, seed_inputs
# Node schema (V3 / Nodes 2.0): like Load VAE, but the VAE is picked from a folder with the DiceForge seed modes, so a series can go
# through every VAE before repeating one.
class RandomVAELoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeRandomVAE",
            display_name="Random VAE",
            category="DiceForge/loaders",
            description="Loads a VAE picked from a folder, like Load VAE, with the DiceForge seed modes (deck, shuffle... go through every VAE before repeating one).",
            search_aliases=["random vae", "vae", "load vae", "vae loader", "random", "seed modes"],
            inputs=[
                folder_input("vae", "VAE"),
                *seed_inputs("VAEs"),
            ],
            outputs=[
                io.Vae.Output(display_name="vae", tooltip="The VAE used for encoding and decoding images to and from latent space."),
                io.String.Output(display_name="vae_name", tooltip="The picked VAE file, for example for the label of Dice Grid."),
            ],
        )
    # Method to run the node again when the files in the folder change.
    @classmethod
    def fingerprint_inputs(cls, folder="(all)", **kwargs):
        return folder_fingerprint("vae", folder)
    # Main method: picks a VAE file of the folder by the seed mode, then loads it with the core Load VAE.
    @classmethod
    def execute(cls, folder="(all)", seed=0, seed_mode="random"):
        name = pick_model_file("vae", folder, seed, seed_mode, "VAE")
        logging.info(f"[DiceForge] Random VAE | {name} | Seed: {seed} ({seed_mode})")
        return io.NodeOutput(nodes.VAELoader().load_vae(name)[0], name)
# Extension entry point for ComfyUI V3 node registration.
class RandomVAELoaderExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [RandomVAELoader]
async def comfy_entrypoint():
    return RandomVAELoaderExtension()
