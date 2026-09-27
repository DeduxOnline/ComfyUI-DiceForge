import logging
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .model_lists import files_in_folder, folder_input
from .seed_modes import MEMORY, SEED_MODES, make_picker, pick_label, seed_mode_tooltip, fingerprint
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
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for the random pick. With deck or sequential, set control after generate to increment.",
                ),
                io.Combo.Input(
                    "seed_mode",
                    options=SEED_MODES,
                    default="random",
                    tooltip=seed_mode_tooltip("diffusion models"),
                    advanced=True,
                ),
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
    # Method to run the node again when the files in the folder change, and every time in the modes that remember earlier runs.
    @classmethod
    def fingerprint_inputs(cls, folder="(all)", seed_mode="random", **kwargs):
        return tuple(files_in_folder("diffusion_models", folder)), fingerprint(seed_mode)
    # Main method: picks a model file of the folder by the seed mode, then loads it with the core Load Diffusion Model.
    @classmethod
    def execute(cls, folder="(all)", seed=0, seed_mode="random", weight_dtype="default"):
        files = files_in_folder("diffusion_models", folder)
        if not files:
            raise ValueError(f"No diffusion model files in {folder}: add some to ComfyUI/models/diffusion_models, or pick another folder.")
        name = pick_label(files, make_picker(seed_mode, seed), seed)
        MEMORY.save()
        logging.info(f"[DiceForge] Random Diffusion Model | {name} | Seed: {seed} ({seed_mode})")
        return io.NodeOutput(nodes.UNETLoader().load_unet(name, weight_dtype)[0], name)
# Extension entry point for ComfyUI V3 node registration.
class RandomDiffusionModelLoaderExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [RandomDiffusionModelLoader]
async def comfy_entrypoint():
    return RandomDiffusionModelLoaderExtension()
