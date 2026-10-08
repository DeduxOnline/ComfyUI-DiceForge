import folder_paths
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
# Value of clip_name2 that loads a single text encoder.
NONE = "None"
# Types of the core Load CLIP (one file) and DualCLIPLoader (two files) nodes, read from those nodes so new types show up here automatically.
def clip_types():
    single = nodes.CLIPLoader.INPUT_TYPES()["required"]["type"][0]
    dual = nodes.DualCLIPLoader.INPUT_TYPES()["required"]["type"][0]
    return single, dual
# Weight types of the core Load Diffusion Model node, read from it for the same reason.
def weight_dtypes():
    return nodes.UNETLoader.INPUT_TYPES()["required"]["weight_dtype"][0]
# Node schema (V3 / Nodes 2.0) that combines Load Diffusion Model with Load CLIP / DualCLIPLoader: the model and its text encoders from one node.
class LoadDiffusionModelCLIP(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        single, dual = clip_types()
        files = folder_paths.get_filename_list("text_encoders")
        return io.Schema(
            node_id="DiceForgeLoadDiffusionModelCLIP",
            display_name="Load Diffusion Model + CLIP",
            category="DiceForge/loaders",
            description="Loads a diffusion model (like Load Diffusion Model) and its text encoders (like Load CLIP, or DualCLIPLoader when clip_name2 is set) in one node.",
            inputs=[
                io.Combo.Input("unet_name", options=folder_paths.get_filename_list("diffusion_models"), tooltip="The diffusion model to load, from models/diffusion_models."),
                io.Combo.Input("clip_name1", options=files, tooltip="The text encoder to load, from models/text_encoders."),
                io.Combo.Input(
                    "clip_name2",
                    options=[NONE] + files,
                    default=NONE,
                    tooltip="The second text encoder. None loads only clip_name1, like Load CLIP. A file loads both, like DualCLIPLoader.",
                    advanced=True,
                ),
                io.Combo.Input(
                    "type",
                    options=list(dict.fromkeys(single + dual)),  # Types of both CLIP nodes, without duplicates.
                    default=single[0],
                    tooltip="The model the text encoders are for. Some types need one file, some need two.",
                    advanced=True,
                ),
                io.Combo.Input("weight_dtype", options=weight_dtypes(), default="default", tooltip="Weight precision of the diffusion model, as in Load Diffusion Model.", advanced=True),
                io.Combo.Input("device", options=["default", "cpu"], default="default", tooltip="Where the text encoders run, as in Load CLIP.", advanced=True),
            ],
            outputs=[
                io.Model.Output(display_name="model", tooltip="The diffusion model."),
                io.Clip.Output(display_name="clip", tooltip="The text encoders."),
            ],
        )
    # Checks the CLIP type against the number of files first (a quick error before the model loads), then loads both through the core nodes.
    @classmethod
    def execute(cls, unet_name, clip_name1, clip_name2, type, weight_dtype="default", device="default"):
        single, dual = clip_types()
        if clip_name2 == NONE and type not in single:
            raise ValueError(f"Type '{type}' needs two text encoders: pick a file in clip_name2, or use a one-file type: {', '.join(single)}.")
        if clip_name2 != NONE and type not in dual:
            raise ValueError(f"Type '{type}' takes one text encoder: set clip_name2 to None, or use a two-file type: {', '.join(dual)}.")
        model = nodes.UNETLoader().load_unet(unet_name, weight_dtype)[0]
        if clip_name2 == NONE:
            clip = nodes.CLIPLoader().load_clip(clip_name1, type, device)[0]
        else:
            clip = nodes.DualCLIPLoader().load_clip(clip_name1, clip_name2, type, device)[0]
        return io.NodeOutput(model, clip)
# Extension entry point for ComfyUI V3 node registration.
class LoadDiffusionModelCLIPExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [LoadDiffusionModelCLIP]
async def comfy_entrypoint():
    return LoadDiffusionModelCLIPExtension()
