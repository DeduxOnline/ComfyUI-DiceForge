import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .sdxl_resolution_list import SDXLResolutionList
# Node schema (V3 / Nodes 2.0): same inputs as SDXL Resolution List, but outputs an empty latent (like Empty Latent Image) plus its width and height.
class SDXLResolutionListLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        schema = SDXLResolutionList.define_schema() # Reusing the inputs of SDXL Resolution List.
        schema.node_id = "SDXLResolutionListLatent"
        schema.display_name = "SDXL Resolution List (Latent)"
        schema.category = "model/latent"
        schema.description = "Pick a resolution from the SDXL list (or at random from the seed) and output an empty latent of that size."
        # Outputs for the node: the empty latent batch, its width and height in pixels, and the seed.
        schema.outputs = [
            io.Latent.Output(display_name="latent", tooltip="Empty latent batch, the same as Empty Latent Image makes for this size."),
            io.Int.Output(display_name="width", tooltip="Width of the latent in pixels."),
            io.Int.Output(display_name="height", tooltip="Height of the latent in pixels."),
            io.Int.Output(display_name="seed", tooltip="The seed used for this run, for example to pass on to KSampler."),
        ]
        return schema
    # Main method to get the size from SDXL Resolution List, then build the empty latent with Empty Latent Image.
    @classmethod
    def execute(cls, **kwargs):
        width, height, batch, seed = SDXLResolutionList.execute(**kwargs).args
        latent = nodes.EmptyLatentImage().generate(width, height, batch)[0]
        return io.NodeOutput(latent, width, height, seed)
# Extension entry point for ComfyUI V3 node registration.
class SDXLResolutionListLatentExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SDXLResolutionListLatent]
async def comfy_entrypoint():
    return SDXLResolutionListLatentExtension()
