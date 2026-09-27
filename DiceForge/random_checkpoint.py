import logging
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .model_lists import files_in_folder, folder_input
from .seed_modes import MEMORY, SEED_MODES, make_picker, pick_label, seed_mode_tooltip, fingerprint
# Node schema (V3 / Nodes 2.0): like Load Checkpoint, but the checkpoint is picked from a folder with the DiceForge seed modes, so a series can go
# through every checkpoint before repeating one.
class RandomCheckpointLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeRandomCheckpoint",
            display_name="Random Checkpoint",
            category="DiceForge/loaders",
            description="Loads a checkpoint picked from a folder, like Load Checkpoint, with the DiceForge seed modes (deck, shuffle... go through every checkpoint before repeating one).",
            search_aliases=["random checkpoint", "random model", "checkpoint", "load checkpoint", "ckpt", "random", "seed modes"],
            inputs=[
                folder_input("checkpoints", "checkpoint"),
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
                    tooltip=seed_mode_tooltip("checkpoints"),
                    advanced=True,
                ),
            ],
            outputs=[
                io.Model.Output(display_name="model", tooltip="The model used for denoising latents."),
                io.Clip.Output(display_name="clip", tooltip="The CLIP model used for encoding text prompts."),
                io.Vae.Output(display_name="vae", tooltip="The VAE used for encoding and decoding images to and from latent space."),
                io.String.Output(display_name="ckpt_name", tooltip="The picked checkpoint file, for example for the file name of the image."),
            ],
        )
    # Method to run the node again when the files in the folder change, and every time in the modes that remember earlier runs.
    @classmethod
    def fingerprint_inputs(cls, folder="(all)", seed_mode="random", **kwargs):
        return tuple(files_in_folder("checkpoints", folder)), fingerprint(seed_mode)
    # Main method: picks a checkpoint file of the folder by the seed mode, then loads it with the core Load Checkpoint.
    @classmethod
    def execute(cls, folder="(all)", seed=0, seed_mode="random"):
        files = files_in_folder("checkpoints", folder)
        if not files:
            raise ValueError(f"No checkpoint files in {folder}: add some to ComfyUI/models/checkpoints, or pick another folder.")
        name = pick_label(files, make_picker(seed_mode, seed), seed)
        MEMORY.save()
        logging.info(f"[DiceForge] Random Checkpoint | {name} | Seed: {seed} ({seed_mode})")
        model, clip, vae = nodes.CheckpointLoaderSimple().load_checkpoint(name)
        return io.NodeOutput(model, clip, vae, name)
# Extension entry point for ComfyUI V3 node registration.
class RandomCheckpointLoaderExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [RandomCheckpointLoader]
async def comfy_entrypoint():
    return RandomCheckpointLoaderExtension()
