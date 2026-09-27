# Package entry point when the ResolutionForge folder is in custom_nodes: registers all nodes.
from typing_extensions import override
from comfy_api.latest import ComfyExtension
from .sdxl_resolution_list import UnifiedSDXLResolution
from .resolution_selector_random import ResolutionSelectorRandom
from .clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative
class UnifiedSDXLResExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [UnifiedSDXLResolution, ResolutionSelectorRandom, CLIPTextEncodePositiveNegative]
async def comfy_entrypoint():
    return UnifiedSDXLResExtension()
