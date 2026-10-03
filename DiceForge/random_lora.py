import logging
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .model_lists import folder_fingerprint, folder_input, pick_model_file, seed_inputs
NO_LORA = "(no LoRA)" # With include_none: one more option that leaves the model and CLIP unchanged.
# Node schema (V3 / Nodes 2.0): like Load LoRA, but the LoRA is picked from a folder with the DiceForge seed modes, so a series can go through every
# LoRA before repeating one. Connect Random Float to the strengths to vary them too.
class RandomLoraLoader(io.ComfyNode):
    loader = nodes.LoraLoader() # The core loader, which keeps the last LoRA file in memory.
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeRandomLora",
            display_name="Random LoRA",
            category="DiceForge/loaders",
            description="Applies a LoRA picked from a folder, like Load LoRA, with the DiceForge seed modes (deck, shuffle... go through every LoRA before repeating one).",
            search_aliases=["random lora", "lora", "load lora", "lora loader", "random", "seed modes"],
            inputs=[
                io.Model.Input("model", tooltip="The diffusion model the LoRA is applied to."),
                io.Clip.Input("clip", optional=True, tooltip="The CLIP model the LoRA is applied to. Leave it unconnected to change only the model."),
                folder_input("loras", "LoRA"),
                io.Float.Input("strength_model", default=1.0, min=-100.0, max=100.0, step=0.01, tooltip="How strongly to modify the diffusion model. This value can be negative."),
                io.Float.Input("strength_clip", default=1.0, min=-100.0, max=100.0, step=0.01, tooltip="How strongly to modify the CLIP model. This value can be negative."),
                *seed_inputs("LoRAs"),
                io.Boolean.Input(
                    "include_none",
                    default=False,
                    tooltip="Add \"no LoRA\" as one more option, so some runs use the model without a LoRA.",
                    advanced=True,
                ),
            ],
            outputs=[
                io.Model.Output(display_name="model", tooltip="The model with the LoRA applied."),
                io.Clip.Output(display_name="clip", tooltip="The CLIP with the LoRA applied (unconnected CLIP input: nothing)."),
                io.String.Output(display_name="lora_name", tooltip="The picked LoRA file, for example for the file name of the image."),
            ],
        )
    # Method to run the node again when the files in the folder change.
    @classmethod
    def fingerprint_inputs(cls, folder="(all)", **kwargs):
        return folder_fingerprint("loras", folder, kwargs.get("include_none"))
    # Main method: picks a LoRA file of the folder by the seed mode, then applies it with the core Load LoRA.
    @classmethod
    def execute(cls, model, folder="(all)", strength_model=1.0, strength_clip=1.0, seed=0, seed_mode="random", include_none=False, clip=None):
        name = pick_model_file("loras", folder, seed, seed_mode, "LoRA", [NO_LORA] if include_none else [])
        logging.info(f"[DiceForge] Random LoRA | {name} | Strength: {strength_model} / {strength_clip} | Seed: {seed} ({seed_mode})")
        if name == NO_LORA:
            return io.NodeOutput(model, clip, "")
        model, lora_clip = cls.loader.load_lora(model, clip, name, strength_model, strength_clip if clip is not None else 0)
        return io.NodeOutput(model, lora_clip if clip is not None else None, name)
# Extension entry point for ComfyUI V3 node registration.
class RandomLoraLoaderExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [RandomLoraLoader]
async def comfy_entrypoint():
    return RandomLoraLoaderExtension()
