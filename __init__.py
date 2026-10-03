# ComfyUI loads this folder when the whole repository is in custom_nodes (ComfyUI Manager, comfy-cli and the ComfyUI Registry install it so, and so
# does a git clone into custom_nodes): the nodes and the frontend are in the DiceForge subfolder.
from .DiceForge import __version__, comfy_entrypoint # noqa: F401
WEB_DIRECTORY = "./DiceForge/web" # Relative to this folder.
