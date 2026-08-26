"""Workflow-scoped SageAttention acceleration for MiniMax H3."""

import logging

import torch
from comfy.patcher_extension import CallbacksMP


logger = logging.getLogger(__name__)


_H3_DIFFUSION_MODELS = {
    "INT8 ConvRot": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "FP8": "minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
    "BF16 (Full)": "minimax_h3_fl2va_bf16.safetensors",
}

_H3_REFERENCE_DIFFUSION_MODELS = {
    "INT8 ConvRot": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "FP8": "minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
    "BF16 (Full)": "minimax_h3_ref2va_bf16.safetensors",
}


class StimmaMiniMaxH3ModelLoader:
    """Load a supported MiniMax H3 diffusion-model precision by friendly name."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"precision": (list(_H3_DIFFUSION_MODELS), {"default": "INT8 ConvRot"})}}

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load"
    CATEGORY = "Stimma/Optimization"

    def load(self, precision):
        import comfy.sd
        import folder_paths

        filename = _H3_DIFFUSION_MODELS.get(precision)
        if filename is None:
            choices = ", ".join(_H3_DIFFUSION_MODELS)
            raise ValueError(f"Unsupported MiniMax H3 precision {precision!r}; expected one of: {choices}")

        model_path = folder_paths.get_full_path_or_raise("diffusion_models", filename)
        return (comfy.sd.load_diffusion_model(model_path, model_options={}),)


class StimmaMiniMaxH3ReferenceModelLoader:
    """Load a supported MiniMax H3 Ref2VA precision by friendly name."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "precision": (
                    list(_H3_REFERENCE_DIFFUSION_MODELS),
                    {"default": "INT8 ConvRot"},
                )
            }
        }

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load"
    CATEGORY = "Stimma/Optimization"

    def load(self, precision):
        import comfy.sd
        import folder_paths

        filename = _H3_REFERENCE_DIFFUSION_MODELS.get(precision)
        if filename is None:
            choices = ", ".join(_H3_REFERENCE_DIFFUSION_MODELS)
            raise ValueError(
                f"Unsupported MiniMax H3 Ref2VA precision {precision!r}; "
                f"expected one of: {choices}"
            )

        model_path = folder_paths.get_full_path_or_raise("diffusion_models", filename)
        return (comfy.sd.load_diffusion_model(model_path, model_options={}),)


class StimmaMiniMaxH3SageAttention:
    """Patch H3's imported attention aliases for one model execution.

    MiniMax imports ``optimized_attention`` by value, so changing Comfy's
    module-level function after startup does not affect H3. This node patches
    only MiniMax's model and VAE aliases during the model lifecycle and restores
    them during cleanup. It intentionally uses the conservative FP8 accumulator;
    the FP16 CUDA kernel can silently return black H3 videos on Blackwell.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"model": ("MODEL",)},
            "optional": {
                "spectrum_enabled": ("BOOLEAN", {"default": False}),
                "blend_weight": ("FLOAT", {"default": 0.50, "min": 0.0, "max": 1.0, "step": 0.01}),
                "degree": ("INT", {"default": 4, "min": 1, "max": 16, "step": 1}),
                "ridge_lambda": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 10.0, "step": 0.01}),
                "window_size": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 16.0, "step": 0.05}),
                "flex_window": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 8.0, "step": 0.05}),
                "warmup_steps": ("INT", {"default": 5, "min": 0, "max": 64, "step": 1}),
                "tail_actual_steps": ("INT", {"default": 1, "min": 0, "max": 64, "step": 1}),
                "max_history": ("INT", {"default": 8, "min": 2, "max": 64, "step": 1}),
                "history_storage": (["system_ram", "vram"], {"default": "system_ram"}),
                "spectrum_debug": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "patch"
    CATEGORY = "Stimma/Optimization"
    EXPERIMENTAL = True

    def patch(
        self,
        model,
        spectrum_enabled=False,
        blend_weight=0.50,
        degree=4,
        ridge_lambda=0.10,
        window_size=2.0,
        flex_window=0.75,
        warmup_steps=5,
        tail_actual_steps=1,
        max_history=8,
        history_storage="system_ram",
        spectrum_debug=False,
    ):
        model_clone = model.clone()
        originals = {}

        @torch.compiler.disable()
        def enable(_model):
            from comfy.ldm.minimax import model as minimax_model
            from comfy.ldm.minimax import vae as minimax_vae

            # The B300 image currently exposes the SageAttention Python API,
            # but its shipped CUDA kernel has no executable image for the
            # B300 runtime.  Let ComfyUI use its native PyTorch attention on
            # that device; otherwise every H3 attention call pays for a
            # failed kernel launch before falling back, which can stall the
            # first diffusion step indefinitely.
            device_name = ""
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(torch.cuda.current_device())
            if "B300" in device_name.upper():
                try:
                    import flash_attn.cute  # noqa: F401
                except Exception as error:
                    originals["b300_skipped"] = True
                    logger.warning(
                        "FlashAttention-4 is unavailable on %s (%s); "
                        "using native PyTorch attention",
                        device_name,
                        error,
                    )
                else:
                    originals["model"] = minimax_model.optimized_attention
                    originals["vae"] = minimax_vae.optimized_attention
                    minimax_model.optimized_attention = _attention_flash4_safe
                    minimax_vae.optimized_attention = _attention_flash4_safe
                    originals["b300_flash4"] = True
                    logger.info(
                        "Enabled workflow-scoped FlashAttention-4 CuTeDSL on %s",
                        device_name,
                    )
                return

            originals["model"] = minimax_model.optimized_attention
            originals["vae"] = minimax_vae.optimized_attention
            minimax_model.optimized_attention = _attention_sage_fp8_safe
            minimax_vae.optimized_attention = _attention_sage_fp8_safe
            logger.info("Enabled workflow-scoped MiniMax H3 SageAttention FP8")

        @torch.compiler.disable()
        def disable(_model):
            from comfy.ldm.minimax import model as minimax_model
            from comfy.ldm.minimax import vae as minimax_vae

            if "model" in originals:
                minimax_model.optimized_attention = originals["model"]
            if "vae" in originals:
                minimax_vae.optimized_attention = originals["vae"]
            logger.info("Restored MiniMax H3 attention")

        model_clone.add_callback(CallbacksMP.ON_PRE_RUN, enable)
        model_clone.add_callback(CallbacksMP.ON_CLEANUP, disable)

        if spectrum_enabled:
            model_clone = _apply_spectrum(
                model_clone,
                blend_weight=blend_weight,
                degree=degree,
                ridge_lambda=ridge_lambda,
                window_size=window_size,
                flex_window=flex_window,
                warmup_steps=warmup_steps,
                tail_actual_steps=tail_actual_steps,
                max_history=max_history,
                history_storage=history_storage,
                debug=spectrum_debug,
            )
        return (model_clone,)


def _apply_spectrum(model, **settings):
    """Delegate to Spectrum when installed without making it a hard dependency."""
    import nodes as comfy_nodes

    spectrum_class = comfy_nodes.NODE_CLASS_MAPPINGS.get("SpectrumApplyMiniMaxH3")
    if spectrum_class is None:
        raise RuntimeError(
            "MiniMax H3 Spectrum was enabled, but ComfyUI-Spectrum-MiniMax-H3 is not installed. "
            "Install https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3 or disable Spectrum."
        )

    return spectrum_class().apply(model=model, enabled=True, **settings)[0]


@torch.compiler.disable()
def _attention_sage_fp8_safe(
    q,
    k,
    v,
    heads,
    mask=None,
    attn_precision=None,
    skip_reshape=False,
    skip_output_reshape=False,
    **kwargs,
):
    """Comfy attention adapter for Sage's accurate FP8 CUDA kernel."""
    from comfy.ldm.modules.attention import AttentionTensorContainer, attention_pytorch
    from sageattention import sageattn_qk_int8_pv_fp8_cuda

    # ComfyUI's MiniMax implementation passes its Q/K/V through the
    # single-owner container wrapper. This adapter is installed directly on
    # the model alias (so Comfy's decorated wrapper is bypassed); consume the
    # containers here before accessing tensor attributes or calling Sage.
    if isinstance(q, AttentionTensorContainer):
        if not (
            isinstance(k, AttentionTensorContainer)
            and isinstance(v, AttentionTensorContainer)
        ):
            raise TypeError("q, k, and v must all be attention tensor containers")
        q, k, v = q.take(), k.take(), v.take()

    if mask is not None:
        return attention_pytorch(
            q,
            k,
            v,
            heads,
            mask=mask,
            skip_reshape=skip_reshape,
            skip_output_reshape=skip_output_reshape,
            **kwargs,
        )

    if skip_reshape:
        batch, _, _, dim_head = q.shape
        tensor_layout = "HND"
    else:
        batch, _, dim = q.shape
        dim_head = dim // heads
        q, k, v = (tensor.view(batch, -1, heads, dim_head) for tensor in (q, k, v))
        tensor_layout = "NHD"

    try:
        out = sageattn_qk_int8_pv_fp8_cuda(
            q,
            k,
            v,
            tensor_layout=tensor_layout,
            is_causal=False,
            sm_scale=kwargs.get("scale"),
            qk_quant_gran="per_warp",
            pv_accum_dtype="fp32+fp32",
        )
    except Exception as error:
        logger.warning("MiniMax H3 SageAttention failed; using PyTorch attention: %s", error)
        return attention_pytorch(
            q,
            k,
            v,
            heads,
            mask=None,
            skip_reshape=True,
            skip_output_reshape=skip_output_reshape,
            **kwargs,
        )

    if tensor_layout == "HND":
        if not skip_output_reshape:
            out = out.transpose(1, 2).reshape(batch, -1, heads * dim_head)
    elif skip_output_reshape:
        out = out.transpose(1, 2)
    else:
        out = out.reshape(batch, -1, heads * dim_head)
    return out


@torch.compiler.disable()
def _attention_flash4_safe(
    q,
    k,
    v,
    heads,
    mask=None,
    attn_precision=None,
    skip_reshape=False,
    skip_output_reshape=False,
    **kwargs,
):
    """Adapter for FlashAttention-4's SM103/B300 CuTeDSL kernel."""
    from comfy.ldm.modules.attention import AttentionTensorContainer, attention_pytorch
    from flash_attn.cute import flash_attn_func

    if isinstance(q, AttentionTensorContainer):
        if not (
            isinstance(k, AttentionTensorContainer)
            and isinstance(v, AttentionTensorContainer)
        ):
            raise TypeError("q, k, and v must all be attention tensor containers")
        q, k, v = q.take(), k.take(), v.take()

    # FA4 expects [batch, sequence, heads, head_dim]. H3's optimized
    # attention receives either Comfy's packed [B, S, hidden] form or its
    # already-shaped [B, H, S, D] form.
    if mask is not None:
        return attention_pytorch(
            q,
            k,
            v,
            heads,
            mask=mask,
            skip_reshape=skip_reshape,
            skip_output_reshape=skip_output_reshape,
            **kwargs,
        )

    if skip_reshape:
        batch, _, _, dim_head = q.shape
        q4, k4, v4 = (
            tensor.transpose(1, 2).contiguous() for tensor in (q, k, v)
        )
    else:
        batch, _, inner_dim = q.shape
        dim_head = inner_dim // heads
        q4, k4, v4 = (
            tensor.view(batch, -1, heads, dim_head).contiguous()
            for tensor in (q, k, v)
        )

    try:
        out, _ = flash_attn_func(
            q4,
            k4,
            v4,
            causal=False,
            softmax_scale=kwargs.get("scale"),
        )
    except Exception as error:
        logger.warning(
            "MiniMax H3 FlashAttention-4 failed; using PyTorch attention: %s",
            error,
        )
        return attention_pytorch(
            q,
            k,
            v,
            heads,
            mask=None,
            skip_reshape=skip_reshape,
            skip_output_reshape=skip_output_reshape,
            **kwargs,
        )

    if skip_reshape:
        return out.transpose(1, 2) if skip_output_reshape else out.transpose(1, 2).reshape(batch, -1, heads * dim_head)
    return out if skip_output_reshape else out.reshape(batch, -1, heads * dim_head)


NODE_CLASS_MAPPINGS = {
    "StimmaMiniMaxH3ModelLoader": StimmaMiniMaxH3ModelLoader,
    "StimmaMiniMaxH3ReferenceModelLoader": StimmaMiniMaxH3ReferenceModelLoader,
    "StimmaMiniMaxH3SageAttention": StimmaMiniMaxH3SageAttention,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StimmaMiniMaxH3ModelLoader": "Stimma MiniMax H3 Model Loader",
    "StimmaMiniMaxH3ReferenceModelLoader": "Stimma MiniMax H3 Reference Model Loader",
    "StimmaMiniMaxH3SageAttention": "Stimma MiniMax H3 SageAttention",
}
