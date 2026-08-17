"""Outpaint geometry nodes."""


class StimmaOutpaintPadding:
    """Percent-of-axis canvas growth to pixel padding.

    The ``outpaint-image`` task contract expresses growth as a percentage of the
    source's CORRESPONDING axis — top/bottom of its height, left/right of its
    width — so one slider means the same canvas whatever the image's
    resolution, and equal values on every edge preserve its aspect ratio.
    ImagePadForOutpaint wants pixels, so something has to convert.

    The arithmetic is deliberately identical to the cloud provider's planner and
    to the app's own Extend Canvas step: truncate ``axis * percent / 100``. All
    three have to agree, or the same tool produces a different canvas depending
    on where it happens to run.
    """

    @classmethod
    def INPUT_TYPES(cls):
        pct = {"default": 0, "min": 0, "max": 100, "step": 1, "display": "number"}
        return {
            "required": {
                "image": ("IMAGE",),
                "left_pct": ("INT", dict(pct)),
                "top_pct": ("INT", dict(pct)),
                "right_pct": ("INT", dict(pct)),
                "bottom_pct": ("INT", dict(pct)),
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT")
    RETURN_NAMES = ("left", "top", "right", "bottom")
    FUNCTION = "execute"
    CATEGORY = "Stimma/Image"

    def execute(self, image, left_pct, top_pct, right_pct, bottom_pct):
        # ComfyUI images are [batch, height, width, channels].
        height = int(image.shape[1])
        width = int(image.shape[2])

        def axis_px(axis: int, percent: int) -> int:
            return int(axis * max(0, min(100, int(percent))) / 100)

        return (
            axis_px(width, left_pct),
            axis_px(height, top_pct),
            axis_px(width, right_pct),
            axis_px(height, bottom_pct),
        )


NODE_CLASS_MAPPINGS = {"StimmaOutpaintPadding": StimmaOutpaintPadding}
