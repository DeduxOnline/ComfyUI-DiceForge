# Package entry point when the ResolutionForge folder is in custom_nodes: registers the Latent resolution nodes, the prompt encoder and the random number nodes.
from typing_extensions import override
from comfy_api.latest import ComfyExtension
from .clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative
from .sdxl_resolution_list_latent import SDXLResolutionListLatent
from .resolution_selector_random_latent import ResolutionSelectorRandomLatent
from .random_int import RandomIntSeedModes
from .random_float import RandomFloatSeedModes
WEB_DIRECTORY = "./web" # Frontend extension: feeds the live size previews of the resolution nodes.
class ResolutionForgeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SDXLResolutionListLatent, ResolutionSelectorRandomLatent, CLIPTextEncodePositiveNegative, RandomIntSeedModes, RandomFloatSeedModes]
async def comfy_entrypoint():
    return ResolutionForgeExtension()
