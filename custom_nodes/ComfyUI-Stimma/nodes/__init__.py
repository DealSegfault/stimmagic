"""Stimma custom nodes for ComfyUI."""

from .tool_info import StimmaToolInfo
from .fields import (
    StimmaPromptParam,
    StimmaImageParam,
    StimmaMaskParam,
    StimmaImagesParam,
    StimmaVideoParam,
    StimmaVideosParam,
    StimmaAudioParam,
    StimmaSeedParam,
)
from .params import (
    StimmaIntParam,
    StimmaFloatParam,
    StimmaStringParam,
    StimmaDropdownParam,
    StimmaResolutionParam,
    StimmaBoolParam,
    StimmaDurationToFrames,
)
from .loras import StimmaLoraLoader, StimmaPairedLoraLoader
from .checkpoints import StimmaCheckpointLoader
from .outputs import StimmaImageOutput, StimmaVideoOutput, StimmaAudioOutput
from .layout import StimmaLayoutGroup
from .stitch_assembler import StimmaVideoStitchAssembler
from .outpaint import StimmaOutpaintPadding
from .minimax_h3_sage import (
    StimmaMiniMaxH3ModelLoader,
    StimmaMiniMaxH3ReferenceModelLoader,
    StimmaMiniMaxH3SageAttention,
)
from .image_crop import StimmaOptionalImageCoverCrop

NODE_CLASS_MAPPINGS = {
    "StimmaToolInfo": StimmaToolInfo,
    "StimmaPromptParam": StimmaPromptParam,
    "StimmaImageParam": StimmaImageParam,
    "StimmaMaskParam": StimmaMaskParam,
    "StimmaImagesParam": StimmaImagesParam,
    "StimmaVideoParam": StimmaVideoParam,
    "StimmaVideosParam": StimmaVideosParam,
    "StimmaAudioParam": StimmaAudioParam,
    "StimmaSeedParam": StimmaSeedParam,
    "StimmaIntParam": StimmaIntParam,
    "StimmaFloatParam": StimmaFloatParam,
    "StimmaStringParam": StimmaStringParam,
    "StimmaDropdownParam": StimmaDropdownParam,
    "StimmaResolutionParam": StimmaResolutionParam,
    "StimmaBoolParam": StimmaBoolParam,
    "StimmaDurationToFrames": StimmaDurationToFrames,
    "StimmaLoraLoader": StimmaLoraLoader,
    "StimmaPairedLoraLoader": StimmaPairedLoraLoader,
    "StimmaCheckpointLoader": StimmaCheckpointLoader,
    "StimmaImageOutput": StimmaImageOutput,
    "StimmaVideoOutput": StimmaVideoOutput,
    "StimmaAudioOutput": StimmaAudioOutput,
    "StimmaLayoutGroup": StimmaLayoutGroup,
    "StimmaVideoStitchAssembler": StimmaVideoStitchAssembler,
    "StimmaOutpaintPadding": StimmaOutpaintPadding,
    "StimmaMiniMaxH3ModelLoader": StimmaMiniMaxH3ModelLoader,
    "StimmaMiniMaxH3ReferenceModelLoader": StimmaMiniMaxH3ReferenceModelLoader,
    "StimmaMiniMaxH3SageAttention": StimmaMiniMaxH3SageAttention,
    "StimmaOptionalImageCoverCrop": StimmaOptionalImageCoverCrop,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StimmaToolInfo": "Stimma Tool Info",
    "StimmaPromptParam": "Stimma Prompt",
    "StimmaImageParam": "Stimma Image",
    "StimmaMaskParam": "Stimma Mask",
    "StimmaImagesParam": "Stimma Images",
    "StimmaVideoParam": "Stimma Video",
    "StimmaVideosParam": "Stimma Videos",
    "StimmaAudioParam": "Stimma Audio",
    "StimmaSeedParam": "Stimma Seed",
    "StimmaIntParam": "Stimma Int",
    "StimmaFloatParam": "Stimma Float",
    "StimmaStringParam": "Stimma String",
    "StimmaDropdownParam": "Stimma Dropdown",
    "StimmaResolutionParam": "Stimma Resolution",
    "StimmaBoolParam": "Stimma Bool",
    "StimmaDurationToFrames": "Stimma Duration to Frames",
    "StimmaLoraLoader": "Stimma LoRA Loader",
    "StimmaPairedLoraLoader": "Stimma Paired LoRA Loader",
    "StimmaCheckpointLoader": "Stimma Checkpoint Loader",
    "StimmaImageOutput": "Stimma Image Output",
    "StimmaVideoOutput": "Stimma Video Output",
    "StimmaAudioOutput": "Stimma Audio Output",
    "StimmaLayoutGroup": "Stimma Layout Group",
    "StimmaVideoStitchAssembler": "Stimma Video Stitch Assembler",
    "StimmaOutpaintPadding": "Stimma Outpaint Padding",
    "StimmaMiniMaxH3ModelLoader": "Stimma MiniMax H3 Model Loader",
    "StimmaMiniMaxH3ReferenceModelLoader": "Stimma MiniMax H3 Reference Model Loader",
    "StimmaMiniMaxH3SageAttention": "Stimma MiniMax H3 SageAttention",
    "StimmaOptionalImageCoverCrop": "Stimma Optional Image Cover Crop",
}
