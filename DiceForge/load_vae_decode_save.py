import nodes
from comfy_api.latest import io, ui
# Last loaded VAE, kept between runs: the latent changes on every run, so without this cache the VAE file would be loaded again each time.
_vae_cache = {"name": None, "vae": None}
# What happens to the decoded images, as in Easy-Use's samplers: Hide (only passed on), Preview (shown on the node, not saved), Save (saved and
# shown, as Save Image does) or Hide&Save (saved, not shown). The images are passed on in every case.
IMAGE_OUTPUTS = ["Hide", "Preview", "Save", "Hide&Save"]
# The VAE used, passed on (for an upscale and a second decode, a hires fix, an inpaint encode...): the one loaded, or the one of the vae input.
def vae_output():
    return io.Vae.Output(display_name="vae", tooltip="The VAE used for decoding, passed on: for example for VAE Encode in a hires fix or inpaint.")
def image_output_input():
    return io.Combo.Input(
        "image_output",
        options=IMAGE_OUTPUTS,
        default="Save",
        optional=True, # Workflows and API prompts made before it save, as they did.
        tooltip="Hide: only pass the images on. Preview: show them on the node without saving. Save: save the PNG files and show them, like Save Image. Hide&Save: save without showing.",
    )
# Decoding as in the core VAE Decode node, then saving as in the core Save Image node: PNG files in the output folder, with the prompt and workflow
# as metadata (or only showing them, by image_output). The decoded images are also passed on. Shared by both nodes below.
def decode_and_save(node_class, vae, samples, filename_prefix, image_output="Save"):
    check_image_output(image_output, "VAE Decode + Save") # Before decoding: a wrong value costs nothing.
    images = decode(vae, samples)
    return io.NodeOutput(images, vae, ui=show_or_save(node_class, images, filename_prefix, image_output))
def check_image_output(image_output, node_name):
    if image_output not in IMAGE_OUTPUTS:
        raise ValueError(f"{node_name}: unknown image_output {image_output!r} (one of {', '.join(IMAGE_OUTPUTS)}).")
# The images shown on the node and/or saved, by image_output: the node's ui (None when nothing is shown).
def show_or_save(node_class, images, filename_prefix, image_output):
    if image_output == "Hide":
        return None
    if image_output == "Preview":
        return ui.PreviewImage(images, cls=node_class)
    if image_output == "Hide&Save":
        ui.ImageSaveHelper.save_images(images, filename_prefix=filename_prefix, folder_type=io.FolderType.output, cls=node_class)
        return None
    return ui.ImageSaveHelper.get_save_images_ui(images, filename_prefix=filename_prefix, cls=node_class)
def decode(vae, samples):
    latent = samples["samples"]
    if latent.is_nested:
        latent = latent.unbind()[0] # A nested latent uses its first tensor.
    images = vae.decode(latent)
    if len(images.shape) == 5:
        images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1]) # 5D (video-style) output is flattened into a batch of frames.
    return images
FILENAME_PREFIX_TOOLTIP = "The prefix for the file to save. A / makes a subfolder. May include %year%, %month%, %day%, %hour%, %minute%, %second%, %width% and %height%."
# Node schema (V3 / Nodes 2.0) that combines Load VAE, VAE Decode and Save Image: it takes a latent, decodes it and saves PNG files with the same metadata as the core Save Image node.
class LoadVAEDecodeSave(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeLoadVAEDecodeSave",
            display_name="Load VAE + Decode + Save",
            category="DiceForge/image",
            inputs=[
                io.Latent.Input("samples", tooltip="The latent to decode."),
                io.Combo.Input(
                    "vae_name",
                    options=nodes.VAELoader.vae_list(nodes.VAELoader),
                    tooltip="The VAE used for decoding. Same list as the core Load VAE node.",
                ),
                io.String.Input(
                    "filename_prefix",
                    default="ComfyUI",
                    tooltip=FILENAME_PREFIX_TOOLTIP,
                ),
                image_output_input(),
            ],
            outputs=[io.Image.Output(display_name="images"), vae_output()],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )
    # Loads the VAE through the core Load VAE node, so taesd, pixel_space and file metadata work as in core, and reuses it while vae_name stays the same.
    @staticmethod
    def load_vae(vae_name):
        if _vae_cache["name"] != vae_name:
            _vae_cache.update(name=None, vae=None)  # Release the previous VAE first; a failed load then retries on the next run.
            vae = nodes.VAELoader().load_vae(vae_name)[0]
            _vae_cache.update(name=vae_name, vae=vae)
        return _vae_cache["vae"]
    @classmethod
    def execute(cls, samples, vae_name, filename_prefix="ComfyUI", image_output="Save"):
        return decode_and_save(cls, cls.load_vae(vae_name), samples, filename_prefix, image_output)
# The same without Load VAE: VAE Decode and Save Image in one node, with the VAE from an input (a checkpoint's VAE, Load VAE, Random VAE...).
class VAEDecodeSave(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeVAEDecodeSave",
            display_name="VAE Decode + Save",
            category="DiceForge/image",
            inputs=[
                io.Latent.Input("samples", tooltip="The latent to decode."),
                io.Vae.Input("vae", tooltip="The VAE used for decoding, for example the VAE output of Load Checkpoint or Load VAE."),
                io.String.Input("filename_prefix", default="ComfyUI", tooltip=FILENAME_PREFIX_TOOLTIP),
                image_output_input(),
            ],
            outputs=[io.Image.Output(display_name="images"), vae_output()],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )
    @classmethod
    def execute(cls, samples, vae, filename_prefix="ComfyUI", image_output="Save"):
        return decode_and_save(cls, vae, samples, filename_prefix, image_output)
