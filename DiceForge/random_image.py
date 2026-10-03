import logging
import os
import numpy as np
import torch
import comfy.model_management
import folder_paths
import node_helpers
from PIL import Image, ImageOps, ImageSequence
from typing_extensions import override
from comfy_api.latest import ComfyExtension, InputImpl, io, ui
from .model_lists import ALL_FOLDERS, image_folders, images_in_folder
from .seed_modes import MEMORY, SEED_MODES, make_picker, pick_label, seed_mode_tooltip, fingerprint
# Image loading with the same steps as Load Image (which only opens files inside ComfyUI's input folder): first the video reader (animated GIFs and
# most formats), then Pillow (frames of the first frame's size, EXIF rotation, RGB, mask from the alpha channel, 1 where transparent). Pillow also
# takes over when the video reader fails, as it does on some WebP files that Load Image can't open.
def load_image_file(path):
    dtype = comfy.model_management.intermediate_dtype()
    device = comfy.model_management.intermediate_device()
    try:
        components = InputImpl.VideoFromFile(path).get_components()
    except Exception:
        components = None
    if components is not None and components.images.shape[0] > 0:
        mask = (1.0 - components.alpha[..., -1]) if components.alpha is not None else torch.zeros((components.images.shape[0], 64, 64))
        return components.images.to(device=device, dtype=dtype), mask.to(device=device, dtype=dtype)
    image = node_helpers.pillow(Image.open, path)
    frames, masks, size = [], [], None
    for frame in ImageSequence.Iterator(image):
        frame = node_helpers.pillow(ImageOps.exif_transpose, frame)
        rgb = frame.convert("RGB")
        size = size or rgb.size
        if rgb.size != size:
            continue
        frames.append(torch.from_numpy(np.array(rgb).astype(np.float32) / 255.0)[None,])
        if "A" in frame.getbands():
            masks.append(1.0 - torch.from_numpy(np.array(frame.getchannel("A")).astype(np.float32) / 255.0)[None,])
        else:
            masks.append(torch.zeros((1, 64, 64), dtype=torch.float32))
    return torch.cat(frames, dim=0).to(device=device, dtype=dtype), torch.cat(masks, dim=0).to(device=device, dtype=dtype)
# Node schema (V3 / Nodes 2.0): like Load Image, but the image is picked from a folder with the DiceForge seed modes, so a series (img2img,
# ControlNet, IP-Adapter...) can go through every image before repeating one.
class RandomImageLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeRandomImage",
            display_name="Random Image",
            category="DiceForge/loaders",
            description="Loads an image picked from a folder, like Load Image, with the DiceForge seed modes (deck, shuffle... go through every image before repeating one).",
            search_aliases=["random image", "load image", "image from folder", "image batch", "random picture", "random", "seed modes"],
            has_intermediate_output=True, # The picked image reaches the node's preview also when the node comes from the cache.
            inputs=[
                io.Combo.Input(
                    "folder",
                    options=image_folders(folder_paths.get_input_directory()),
                    default=ALL_FOLDERS,
                    tooltip="The folder in ComfyUI/input to pick the image from, subfolders included. (all): every image in input. Refresh the node definitions (R) after adding folders.",
                ),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for the random pick. With deck or sequential, set control after generate to increment.",
                ),
                io.Combo.Input(
                    "seed_mode",
                    options=SEED_MODES,
                    default="random",
                    tooltip=seed_mode_tooltip("images"),
                    advanced=True,
                ),
                io.String.Input(
                    "path",
                    default="",
                    tooltip="Any folder on this computer to pick from instead of the input folder, for example D:/refs/poses (subfolders included). Empty: use folder.",
                    advanced=True,
                ),
            ],
            outputs=[
                io.Image.Output(display_name="image", tooltip="The picked image (all frames of an animated image)."),
                io.Mask.Output(display_name="mask", tooltip="The mask from the image's alpha channel (1 where transparent), as in Load Image."),
                io.String.Output(display_name="file_name", tooltip="The picked file, relative to the folder, for example for the file name of the result."),
            ],
        )
    # The folder to list, and the images in it.
    @staticmethod
    def source(folder, path):
        if path.strip():
            root = os.path.abspath(os.path.expanduser(path.strip().strip('"')))
            if not os.path.isdir(root):
                raise ValueError(f"Random Image: the path {root} is not a folder.")
            return root, images_in_folder(root, ALL_FOLDERS)
        root = folder_paths.get_input_directory()
        return root, images_in_folder(root, folder)
    # Method to run the node again when images in the folder are added, removed or changed, and every time in the modes that remember earlier runs.
    @classmethod
    def fingerprint_inputs(cls, folder=ALL_FOLDERS, path="", seed_mode="random", **kwargs):
        try:
            root, files = cls.source(folder, path)
        except ValueError:
            return None # The run reports the error.
        return tuple((name, os.path.getmtime(os.path.join(root, name))) for name in files), fingerprint(seed_mode)
    # Main method: picks an image of the folder by the seed mode, then loads it like Load Image and shows it on the node.
    @classmethod
    def execute(cls, folder=ALL_FOLDERS, seed=0, seed_mode="random", path=""):
        root, files = cls.source(folder, path)
        if not files:
            raise ValueError(f"Random Image: no images in {root if path.strip() else 'input/' + folder}. Supported: png, jpg, webp, bmp, gif, tiff.")
        name = pick_label(files, make_picker(seed_mode, seed), seed)
        MEMORY.save()
        logging.info(f"[DiceForge] Random Image | {name} | Seed: {seed} ({seed_mode})")
        try:
            image, mask = load_image_file(os.path.join(root, name))
        except (OSError, ValueError, RuntimeError) as error: # A damaged or truncated file: say which one, so it can be fixed or removed.
            raise ValueError(f"Random Image: {name} can't be read ({error}). Fix or remove it, or use another seed.") from None
        # The node's preview (web/image_preview.js): the picked file with its size and the seed it came from. A file of the input folder is shown
        # from there (it stays, also after a restart); one from another folder through a temporary copy of its first frame, like Preview Image.
        if path.strip():
            view = ui.PreviewImage(image[:1], cls=cls).values[0]
        else:
            subfolder, file = os.path.split(os.path.relpath(os.path.join(root, name), folder_paths.get_input_directory()))
            view = {"filename": file, "subfolder": subfolder.replace(os.sep, "/"), "type": "input"}
        shown = {"file": name, "folder": root if path.strip() else "input" + ("" if folder == ALL_FOLDERS else f"/{folder}"), "width": int(image.shape[2]),
                 "height": int(image.shape[1]), "frames": int(image.shape[0]), "seed": seed, "seed_mode": seed_mode, "view": view}
        return io.NodeOutput(image, mask, name, ui={"dice_forge_image": [shown]})
# Extension entry point for ComfyUI V3 node registration.
class RandomImageLoaderExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [RandomImageLoader]
async def comfy_entrypoint():
    return RandomImageLoaderExtension()
