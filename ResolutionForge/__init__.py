# Package entry point when the ResolutionForge folder is in custom_nodes: registers the Latent resolution nodes and the prompt encoder.
from typing_extensions import override
from comfy_api.latest import ComfyExtension
from .clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative
from .sdxl_resolution_list_latent import SDXLResolutionListLatent
from .resolution_selector_random_latent import ResolutionSelectorRandomLatent
WEB_DIRECTORY = "./web" # Frontend extension: feeds the live size previews of the resolution nodes.
class ResolutionForgeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SDXLResolutionListLatent, ResolutionSelectorRandomLatent, CLIPTextEncodePositiveNegative]
async def comfy_entrypoint():
    return ResolutionForgeExtension()
