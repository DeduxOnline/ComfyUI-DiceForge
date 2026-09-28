# Package entry point when the repository is cloned into custom_nodes: registers all nodes.
from typing_extensions import override
from comfy_api.latest import ComfyExtension
from .sdxl_resolution_list import UnifiedSDXLResolution
from .resolution_selector_random import ResolutionSelectorRandom
from .vae_decode_save import LoadVAEDecodeSave
from .clip_loader_single_dual import CLIPLoaderSingleDual
class UnifiedSDXLResExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [UnifiedSDXLResolution, ResolutionSelectorRandom, LoadVAEDecodeSave, CLIPLoaderSingleDual]
async def comfy_entrypoint():
    return UnifiedSDXLResExtension()
