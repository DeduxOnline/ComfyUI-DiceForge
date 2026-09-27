# Package entry point when the ResolutionForge folder is in custom_nodes: registers all nodes.
from typing_extensions import override
from comfy_api.latest import ComfyExtension
from .sdxl_resolution_list import SDXLResolutionList
from .resolution_selector_random import ResolutionSelectorRandom
from .clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative
from .sdxl_resolution_list_latent import SDXLResolutionListLatent
from .resolution_selector_random_latent import ResolutionSelectorRandomLatent
class ResolutionForgeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SDXLResolutionList, ResolutionSelectorRandom, SDXLResolutionListLatent, ResolutionSelectorRandomLatent, CLIPTextEncodePositiveNegative]
async def comfy_entrypoint():
    return ResolutionForgeExtension()
