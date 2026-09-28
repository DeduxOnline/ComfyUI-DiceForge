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
# Node schema (V3 / Nodes 2.0) that combines Load CLIP and DualCLIPLoader: one text encoder when clip_name2 is None, two otherwise.
class CLIPLoaderSingleDual(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        single, dual = clip_types()
        files = folder_paths.get_filename_list("text_encoders")
        return io.Schema(
            node_id="CLIPLoaderSingleDual",
            display_name="Load CLIP (Single / Dual)",
            category="utils",
            description=f"{nodes.CLIPLoader.DESCRIPTION}\n\n{nodes.DualCLIPLoader.DESCRIPTION}",
            inputs=[
                io.Combo.Input("clip_name1", options=files, tooltip="The text encoder to load."),
                io.Combo.Input(
                    "clip_name2",
                    options=[NONE] + files,
                    default=NONE,
                    tooltip="The second text encoder. None loads only clip_name1, like Load CLIP. A file loads both, like DualCLIPLoader.",
                ),
                io.Combo.Input(
                    "type",
                    options=list(dict.fromkeys(single + dual)),  # Types of both nodes, without duplicates.
                    default=single[0],
                    tooltip="The model the text encoders are for. Some types need one file, some need two.",
                ),
                io.Combo.Input("device", options=["default", "cpu"], default="default", optional=True, advanced=True),
            ],
            outputs=[io.Clip.Output()],
        )
    # Loads through the core node that matches the number of files, after checking that the type works with that number.
    @classmethod
    def execute(cls, clip_name1, clip_name2, type, device="default"):
        single, dual = clip_types()
        if clip_name2 == NONE:
            if type not in single:
                raise ValueError(f"Type '{type}' needs two text encoders: pick a file in clip_name2, or use a one-file type: {', '.join(single)}.")
            return io.NodeOutput(nodes.CLIPLoader().load_clip(clip_name1, type, device)[0])
        if type not in dual:
            raise ValueError(f"Type '{type}' takes one text encoder: set clip_name2 to None, or use a two-file type: {', '.join(dual)}.")
        return io.NodeOutput(nodes.DualCLIPLoader().load_clip(clip_name1, clip_name2, type, device)[0])
# Extension entry point for ComfyUI V3 node registration.
class CLIPLoaderSingleDualExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [CLIPLoaderSingleDual]
async def comfy_entrypoint():
    return CLIPLoaderSingleDualExtension()
