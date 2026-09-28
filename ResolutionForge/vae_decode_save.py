import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io, ui
# Last loaded VAE, kept between runs: the latent changes on every run, so without this cache the VAE file would be loaded again each time.
_vae_cache = {"name": None, "vae": None}
# Node schema (V3 / Nodes 2.0) that combines Load VAE, VAE Decode and Save Image: it takes a latent, decodes it and saves PNG files with the same metadata as the core Save Image node.
class LoadVAEDecodeSave(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LoadVAEDecodeSave",
            display_name="Load VAE + Decode + Save",
            category="utils",
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
                    tooltip="The prefix for the file to save. May include formatting tokens such as %date:yyyy-MM-dd% or %Empty Latent Image.width%.",
                ),
            ],
            outputs=[io.Image.Output(display_name="images")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )
    # Loads the VAE through the core Load VAE node, so taesd, pixel_space and file metadata work as in core, and reuses it while vae_name stays the same.
    @staticmethod
    def load_vae(vae_name):
        if _vae_cache["name"] != vae_name:
            _vae_cache["name"], _vae_cache["vae"] = None, None  # Release the previous VAE first; a failed load then retries on the next run.
            _vae_cache["vae"] = nodes.VAELoader().load_vae(vae_name)[0]
            _vae_cache["name"] = vae_name
        return _vae_cache["vae"]
    @classmethod
    def execute(cls, samples, vae_name, filename_prefix="ComfyUI"):
        vae = cls.load_vae(vae_name)
        # Decoding as in the core VAE Decode node: a nested latent uses its first tensor, and 5D (video-style) output is flattened into a batch of frames.
        latent = samples["samples"]
        if latent.is_nested:
            latent = latent.unbind()[0]
        images = vae.decode(latent)
        if len(images.shape) == 5:
            images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
        # Saving as in the core Save Image node: PNG files in the output folder, with the prompt and workflow as metadata. The decoded images are also passed on.
        return io.NodeOutput(images, ui=ui.ImageSaveHelper.get_save_images_ui(images, filename_prefix=filename_prefix, cls=cls))
# Extension entry point for ComfyUI V3 node registration.
class VAEDecodeSaveExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [LoadVAEDecodeSave]
async def comfy_entrypoint():
    return VAEDecodeSaveExtension()
