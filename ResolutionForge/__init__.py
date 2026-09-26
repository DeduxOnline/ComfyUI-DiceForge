# Package entry point when the repository is cloned into custom_nodes: registers both nodes.
from typing_extensions import override
from comfy_api.latest import ComfyExtension
from .sdxl_resolution_list import UnifiedSDXLResolution
from .resolution_selector_random import ResolutionSelectorRandom
class UnifiedSDXLResExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [UnifiedSDXLResolution, ResolutionSelectorRandom]
async def comfy_entrypoint():
    return UnifiedSDXLResExtension()
