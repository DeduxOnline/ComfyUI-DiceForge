# DiceForge: controlled randomness for ComfyUI. Package entry point when the DiceForge folder is in custom_nodes: registers the resolution nodes, the prompt encoder, the random number nodes, the random model and image loaders, LoRA Stack and Dice Grid, which all pick with the seed modes of seed_modes.py.
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
from .dice_grid import DiceGrid
from .random_sampler import RandomSampler
from .random_vae import RandomVAELoader
from .load_vae_decode_save import LoadVAEDecodeSave, VAEDecodeSave
from .load_diffusion_model_clip import LoadDiffusionModelCLIP
from .lora_stack import LoraStack
from .hires_upscale import HiresUpscale
from .danbooru_enhancer import DanbooruTagEnhancer
from .variation_seed import VariationSeed
from .xy_plot import XYPlot # Also the route of its preview on the node (web/xy_plot.js).
from . import model_info # Server routes of the Model info dialog (web/model_info.js).
from . import wildcards_api # Server routes of the Wildcard Browser and the __ autocomplete (web/wildcards.js).
from . import tag_autocomplete # Server routes of the Danbooru / e621 tag autocomplete (web/tag_autocomplete.js).
from . import prompt_styles # Server routes of the prompt styles in CLIP Dual Text Encode's menu (web/prompt_styles.js).
from . import sampler_presets # Server routes of the KSampler presets in the node menu (web/sampler_presets.js).
from . import model_manager # Server routes that manage LoRA files: Civitai search and download, rename and delete (web/civitai.js, web/model_browser.js).
__version__ = "1.0.0" # As in pyproject.toml and CHANGELOG.md (tests/test_release.py).
WEB_DIRECTORY = "./web" # Frontend extension: feeds the live size previews of the resolution nodes.
class DiceForgeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SDXLResolutionListLatent, ResolutionSelectorRandomLatent, CLIPTextEncodePositiveNegative, RandomIntSeedModes, RandomFloatSeedModes, RandomLoraLoader, RandomCheckpointLoader, RandomDiffusionModelLoader, RandomImageLoader, DiceGrid, RandomSampler, RandomVAELoader, LoadVAEDecodeSave, VAEDecodeSave, LoadDiffusionModelCLIP, LoraStack, XYPlot, VariationSeed, HiresUpscale, DanbooruTagEnhancer]
async def comfy_entrypoint():
    return DiceForgeExtension()
