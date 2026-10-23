import logging
import nodes
from comfy_api.latest import io
from .model_lists import folder_fingerprint, folder_input, pick_model_file, seed_inputs
# Node schema (V3 / Nodes 2.0): like Load Diffusion Model, but the model is picked from a folder with the DiceForge seed modes, so a series can go
# through every model before repeating one.
class RandomDiffusionModelLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeRandomDiffusionModel",
            display_name="Random Diffusion Model",
            category="DiceForge/loaders",
            description="Loads a diffusion model picked from a folder, like Load Diffusion Model, with the DiceForge seed modes (deck, shuffle... go through every model before repeating one).",
            search_aliases=["random diffusion model", "random unet", "unet", "load diffusion model", "diffusion model", "random", "seed modes"],
            inputs=[
                folder_input("diffusion_models", "diffusion model"),
                *seed_inputs("diffusion models"),
                io.Combo.Input(
                    "weight_dtype",
                    options=["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"],
                    default="default",
                    tooltip="Weight precision to load the model in, as in Load Diffusion Model.",
                    advanced=True,
                ),
            ],
            outputs=[
                io.Model.Output(display_name="model", tooltip="The model used for denoising latents."),
                io.String.Output(display_name="model_name", tooltip="The picked model file, for example for the file name of the image."),
            ],
        )
    # Method to run the node again when the files in the folder change.
    @classmethod
    def fingerprint_inputs(cls, folder="(all)", **kwargs):
        return folder_fingerprint("diffusion_models", folder)
    # Main method: picks a model file of the folder by the seed mode, then loads it with the core Load Diffusion Model.
    @classmethod
    def execute(cls, folder="(all)", seed=0, seed_mode="random", weight_dtype="default"):
        name = pick_model_file("diffusion_models", folder, seed, seed_mode, "diffusion model")
        logging.info(f"[DiceForge] Random Diffusion Model | {name} | Seed: {seed} ({seed_mode})")
        return io.NodeOutput(nodes.UNETLoader().load_unet(name, weight_dtype)[0], name)
