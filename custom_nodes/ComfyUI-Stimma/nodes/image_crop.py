"""Image preprocessing nodes for Stimma workflows."""

import comfy.utils


class StimmaOptionalImageCoverCrop:
    """Center-crop an optional image to exactly fill a target canvas."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 768, "min": 1, "max": 16384}),
                "height": ("INT", {"default": 768, "min": 1, "max": 16384}),
            },
            "optional": {"image": ("IMAGE",)},
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "crop"
    CATEGORY = "Stimma/Image"

    def crop(self, width, height, image=None):
        if image is None:
            return (None,)

        channels_first = image.movedim(-1, 1)
        cropped = comfy.utils.common_upscale(
            channels_first,
            width,
            height,
            "lanczos",
            "center",
        )
        return (cropped.movedim(1, -1),)


NODE_CLASS_MAPPINGS = {
    "StimmaOptionalImageCoverCrop": StimmaOptionalImageCoverCrop,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StimmaOptionalImageCoverCrop": "Stimma Optional Image Cover Crop",
}
