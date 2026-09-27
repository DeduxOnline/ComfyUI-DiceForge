# Package entry point when the ResolutionForge folder is in custom_nodes: registers all nodes.
from typing_extensions import override
from comfy_api.latest import ComfyExtension
from .sdxl_resolution_list import UnifiedSDXLResolution
from .resolution_selector_random import ResolutionSelectorRandom
from .clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative
from .sdxl_resolution_list_latent import SDXLResolutionListLatent
from .resolution_selector_random_latent import ResolutionSelectorRandomLatent
from .prompt_director import PromptDirector
class UnifiedSDXLResExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [UnifiedSDXLResolution, ResolutionSelectorRandom, SDXLResolutionListLatent, ResolutionSelectorRandomLatent, CLIPTextEncodePositiveNegative, PromptDirector]
async def comfy_entrypoint():
    return UnifiedSDXLResExtension()
