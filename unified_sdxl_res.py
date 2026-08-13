import random
# List of valid resolutions for SDXL canvas sizes, including random options for dynamic selection.
RESOLUTIONS = {
    "1024 x 1024 (1:1 Square)": (1024, 1024),
    "1152 x 896 (9:7 Landscape)": (1152, 896),
    "896 x 1152 (7:9 Portrait)": (896, 1152),
    "1216 x 832 (3:2 Widescreen)": (1216, 832),
    "832 x 1216 (2:3 Tall Portrait)": (832, 1216),
    "1344 x 768 (16:9 Desktop view)": (1344, 768),
    "768 x 1344 (9:16 Mobile view)": (768, 1344),
    "1536 x 640 (21:9 Cinematic)": (1536, 640),
    "640 x 1536 (9:21 Vertical Scroll)": (640, 1536),
    "1536 x 1536 (1:1 High-Res Square)": (1536, 1536),
    "1152 x 1536 (7:9 High-Res Portrait)": (1152, 1536),
    "1536 x 1152 (9:7 High-Res Landscape)": (1536, 1152),
    "1024 x 1536 (2:3 High-Res Tall Portrait)": (1024, 1536),
    "1536 x 1024 (3:2 High-Res Widescreen)": (1536, 1024),
    "1536 x 864 (16:9 High-Res Desktop view)": (1536, 864),
    "864 x 1536 (9:16 High-Res Mobile view)": (864, 1536),
}
RANDOM_CANDIDATES = {
    "Any Listed": (
        (1024, 1024),
        (1152, 896),
        (896, 1152),
        (1216, 832),
        (832, 1216),
        (1344, 768),
        (768, 1344),
    ),
    "Any High-Res Listed": (
        (1536, 1536),
        (1152, 1536),
        (1536, 1152),
        (1024, 1536),
        (1536, 1024),
        (1536, 864),
        (864, 1536),
    ),
    "Vertical Listed (width < height)": (
        (896, 1152),
        (832, 1216),
        (768, 1344),
    ),
    "Horizontal Listed (width > height)": (
        (1152, 896),
        (1216, 832),
        (1344, 768),
    ),
    "Vertical High-Res Listed (width < height)": (
        (1152, 1536),
        (1024, 1536),
        (864, 1536),
    ),
    "Horizontal High-Res Listed (width > height)": (
        (1536, 1152),
        (1536, 1024),
        (1536, 864),
    ),
}
RANDOM_CHAOS = {
    "Random Small (up to 512^2 pixels)": (512, 512),
    "Random Medium (up to 1024^2 pixels)": (1024, 1024),
    "Random Large (up to 1536^2 pixels)": (1536, 1536),
}
# Node input types and configuration for SDXL resolution selection, including randomization and VAE alignment.
class UnifiedSDXLResolution:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "resolution": (
                    list(RESOLUTIONS) + list(RANDOM_CANDIDATES) + list(RANDOM_CHAOS),
                    {
                        "default": "1024 x 1024 (1:1 Square)",
                        "tooltip": "Resolution list for canvas. Random options will select a random resolution from the list each time.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "tooltip": "Seed for random resolution selection.",
                    },
                ),
                "multiply": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.1,
                        "max": 10.0,
                        "step": 0.05,
                        "tooltip": "Multiply the width and height by this value (Use vae_alignment for VAE compatibility of resolutions).",
                    },
                ),
                "vae_alignment": (
                    "INT",
                    {
                        "default": 64,
                        "min": 8,
                        "max": 256,
                        "step": 8,
                        "tooltip": "Round dimensions to nearest multiple of this value (VAE requirement).",
                    },
                ),
                "batch": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": 32,
                        "step": 1,
                        "tooltip": "Number of images to generate in a batch.",
                    },
                ),
            }
        }
    # Return types and names for the node, specifying the output as width, height, and batch size.
    RETURN_TYPES = ("INT", "INT", "INT")
    RETURN_NAMES = ("width", "height", "batch")
    FUNCTION = "get_res"
    CATEGORY = "utils"
    # Method to indicate that the node's output does not change based on input parameters, returning NaN to signify no change.
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")
    # Vae alignment rounding method to ensure width and height are multiples of the specified alignment value, with a minimum of the alignment value itself.
    @staticmethod
    def round_for_vae(width, height, vae_alignment=64):
        return (
            max(vae_alignment, width // vae_alignment * vae_alignment),
            max(vae_alignment, height // vae_alignment * vae_alignment),
        )
    # Chaos-based random pixel range selection method, generating a width and height within a specified range based on the maximum width and height provided.
    @staticmethod
    def range_pixels(rng, max_width, max_height):
        max_pixels = max_width * max_height # Calculate the maximum number of pixels based on the provided width and height.
        range = max_width * 30 // 100  # Step size for width selection in both directions.
        width = rng.randint(max_width - range, max_width + range) # Range for width selection, allowing for some variation around the maximum width.
        height = max_pixels // width
        return width, height  if rng.random() < 0.5 else height, width  # Randomly return either (width, height) or (height, width) to introduce variability in the output resolution.
    # Main method to get the resolution based on the selected option, applying randomization and VAE alignment as needed, and returning the final width, height, and batch size.
    def get_res(self, resolution, seed=0, multiply=1.0, vae_alignment=64, batch=1):
        rng = random.Random(seed) #Seed behavior for reproducibility of random selections.
        # Switching logic to determine the width and height based on the selected resolution option, handling random candidates and chaos options appropriately.
        if resolution in RANDOM_CANDIDATES:
            width, height = rng.choice(RANDOM_CANDIDATES[resolution])#Returning a random resolution from the specified list of candidates.
        elif resolution in RANDOM_CHAOS:
            width, height = self.range_pixels(rng, *RANDOM_CHAOS[resolution])#Returning a random resolution within the specified pixel range for chaos options.
        else:
            width, height = RESOLUTIONS[resolution]#Returning the fixed resolution for standard options.
        # Applying the multiply factor to the width and height, followed by rounding for VAE alignment to ensure compatibility with the model's requirements.
        width, height = self.round_for_vae(
            round(width * multiply),
            round(height * multiply),
            vae_alignment
        )
        # Logging the final resolution, VAE alignment, seed, and batch size for debugging and verification purposes.
        print(
            f"[SDXL Resolution] Size: {width}x{height} | VAE Alignment: {vae_alignment} | Seed: {seed} | Batch: {batch}"
        )
        return width, height, batch
# Node class and display name mappings for integration into the ComfyUI framework, allowing the UnifiedSDXLResolution node to be recognized and displayed appropriately.
NODE_CLASS_MAPPINGS = {"UnifiedSDXLResolution": UnifiedSDXLResolution,}
NODE_DISPLAY_NAME_MAPPINGS = {"UnifiedSDXLResolution": "SDXL Resolution List",}
