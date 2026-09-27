import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .resolution_selector_random import ResolutionSelectorRandom
# Node schema (V3 / Nodes 2.0): same inputs as Resolution Selector (Random), but outputs an empty latent (like Empty Latent Image) plus its width and height.
class ResolutionSelectorRandomLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        schema = ResolutionSelectorRandom.define_schema() # Reusing the inputs of Resolution Selector (Random).
        schema.node_id = "ResolutionSelectorRandomLatent"
        schema.display_name = "Resolution Selector (Random, Latent)"
        schema.category = "model/latent"
        schema.description = "Calculate a size from an aspect ratio and a megapixel target (or a random aspect ratio from the seed) and output an empty latent of that size."
        # Outputs for the node: the empty latent batch, its width and height in pixels, and the seed.
        schema.outputs = [
            io.Latent.Output(display_name="latent", tooltip="Empty latent batch, the same as Empty Latent Image makes for this size."),
            io.Int.Output(display_name="width", tooltip="Width of the latent in pixels."),
            io.Int.Output(display_name="height", tooltip="Height of the latent in pixels."),
            io.Int.Output(display_name="seed", tooltip="The seed used for this run, for example to pass on to KSampler."),
        ]
        return schema
    # Main method to get the size from Resolution Selector (Random), then build the empty latent with Empty Latent Image.
    @classmethod
    def execute(cls, **kwargs):
        width, height, batch, seed = ResolutionSelectorRandom.execute(**kwargs).args
        latent = nodes.EmptyLatentImage().generate(width, height, batch)[0]
        return io.NodeOutput(latent, width, height, seed)
# Extension entry point for ComfyUI V3 node registration.
class ResolutionSelectorRandomLatentExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [ResolutionSelectorRandomLatent]
async def comfy_entrypoint():
    return ResolutionSelectorRandomLatentExtension()
