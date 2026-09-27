# DiceForge: controlled randomness for ComfyUI. Package entry point when the DiceForge folder is in custom_nodes: registers the resolution nodes, the prompt encoder, the random number nodes and the random model and image loaders, which all pick with the seed modes of seed_modes.py.
from typing_extensions import override
from comfy_api.latest import ComfyExtension
from .clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative
from .sdxl_resolution_list_latent import SDXLResolutionListLatent
from .resolution_selector_random_latent import ResolutionSelectorRandomLatent
from .random_int import RandomIntSeedModes
from .random_float import RandomFloatSeedModes
from .random_lora import RandomLoraLoader
from .random_checkpoint import RandomCheckpointLoader
from .random_diffusion_model import RandomDiffusionModelLoader
from .random_image import RandomImageLoader
WEB_DIRECTORY = "./web" # Frontend extension: feeds the live size previews of the resolution nodes.
class DiceForgeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SDXLResolutionListLatent, ResolutionSelectorRandomLatent, CLIPTextEncodePositiveNegative, RandomIntSeedModes, RandomFloatSeedModes, RandomLoraLoader, RandomCheckpointLoader, RandomDiffusionModelLoader, RandomImageLoader]
async def comfy_entrypoint():
    return DiceForgeExtension()
