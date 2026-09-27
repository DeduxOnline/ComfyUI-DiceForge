from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
# Node schema (V3 / Nodes 2.0) like CLIP Text Encode (Prompt), but with a positive prompt on top, a negative prompt below, and one conditioning output for each.
class CLIPTextEncodePositiveNegative(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="CLIPTextEncodePositiveNegative",
            display_name="CLIP Text Encode (Positive/Negative)",
            category="model/conditioning",
            description="Encodes a positive and a negative prompt with the same CLIP model, outputting a conditioning for each.",
            search_aliases=["text", "prompt", "positive prompt", "negative prompt", "encode text", "text encoder", "encode prompt"],
            inputs=[
                io.String.Input(
                    "positive",
                    multiline=True,
                    dynamic_prompts=True,
                    tooltip="The positive prompt: what the image should contain.",
                ),
                io.String.Input(
                    "negative",
                    multiline=True,
                    dynamic_prompts=True,
                    tooltip="The negative prompt: what the image should avoid.",
                ),
                io.Clip.Input(
                    "clip",
                    tooltip="The CLIP model used for encoding both prompts.",
                ),
            ],
            # Outputs for the node: positive and negative conditioning.
            outputs=[
                io.Conditioning.Output(display_name="positive", tooltip="Conditioning from the positive prompt."),
                io.Conditioning.Output(display_name="negative", tooltip="Conditioning from the negative prompt."),
            ],
        )
    # Encoding method, same as CLIP Text Encode (Prompt).
    @staticmethod
    def encode(clip, text):
        tokens = clip.tokenize(text)
        return clip.encode_from_tokens_scheduled(tokens)
    # Main method to encode both prompts and return the positive and negative conditioning.
    @classmethod
    def execute(cls, positive, negative, clip):
        if clip is None:
            raise RuntimeError("ERROR: clip input is invalid: None\n\nIf the clip is from a checkpoint loader node your checkpoint does not contain a valid clip or text encoder model.")
        return io.NodeOutput(cls.encode(clip, positive), cls.encode(clip, negative))
# Extension entry point for ComfyUI V3 node registration.
class CLIPTextEncodePositiveNegativeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [CLIPTextEncodePositiveNegative]
async def comfy_entrypoint():
    return CLIPTextEncodePositiveNegativeExtension()
