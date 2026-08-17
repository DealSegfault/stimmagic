"""Animated live previews for video generations.

Stock ComfyUI decodes only the FIRST frame of a 5D video latent for its live
sampler preview, so video jobs preview as a static refining image. This module
wraps ``latent_preview.get_previewer`` so video latents additionally produce a
small looping animated WebP each step (latent2rgb over an evenly-spaced subset
of frames — a per-frame linear map, cheap even on large clips). The executor
forwards it over STP as an ``image/webp`` preview payload; browsers loop
animated WebP in a plain ``<img>``, so the client needs no player.

Format: an animated WebP the browser plays directly.

Delivery: the sampling runs in whichever ComfyUI instance the executor
dispatched the job to — with multi-instance setups that is usually NOT the
process hosting the STP server, so an in-process handoff cannot work. The
animation is sent on the executing instance's own client websocket (the
monitoring socket the executor already holds open to that instance) as a
custom binary event, alongside ComfyUI's native preview frames.

Binary layout: [4B event][WebP bytes]
"""

import io
import itertools
import logging
import threading
import time

logger = logging.getLogger(__name__)

# A single prompt can run SEVERAL sampler passes (MiniMax H3 and other
# multi-expert / base+refiner pipelines), and ComfyUI builds a fresh previewer
# per pass. Left alone they all emit, interleaved, each at its own denoise
# level — so the client alternates between two different versions of the clip.
# That reads as motion jumping around or running backwards, and flips to a
# near-black frame whenever the less-developed pass wins a turn.
#
# Ownership is therefore monotonic per client: the highest-sequence previewer
# that has emitted owns the stream, and earlier ones go quiet for good. A
# genuine handoff (base finishes, refiner starts) transfers ownership forward
# and never back.
_SEQ = itertools.count(1)
_STATE_LOCK = threading.Lock()
_OWNER_SEQ = {}   # client_id -> owning previewer sequence
_LAST_EMIT = {}   # client_id -> monotonic timestamp of last emit


def _claim(client_id: str, seq: int, min_interval: float) -> bool:
    """Take/hold the emit slot for this client, respecting pacing."""
    with _STATE_LOCK:
        owner = _OWNER_SEQ.get(client_id)
        if owner is not None and seq < owner:
            return False  # superseded by a later sampler pass
        if owner != seq:
            _OWNER_SEQ[client_id] = seq
            _LAST_EMIT.pop(client_id, None)
        now = time.monotonic()
        last = _LAST_EMIT.get(client_id, 0.0)
        if now - last < min_interval:
            return False
        _LAST_EMIT[client_id] = now
        return True

# Custom binary websocket event ("STVP") carrying an animated WebP payload.
# Far outside ComfyUI's BinaryEventTypes range; only our executor consumes it.
STIMMA_VIDEO_PREVIEW_EVENT = 0x53545650

_MAX_FRAMES = 24     # animation frame budget (evenly spaced over the clip)
_TARGET_WIDTH = 320  # upscaled from latent resolution
_STIMMA_PREVIEW_SIZE = 1024  # single-frame preview max edge, our prompts only
_ASSUMED_FPS = 24.0  # video fps assumption for real-time preview playback

# Playback is paced toward real time: a latent frame covers
# `temporal_downscale_ratio` real frames (4 for H3, 8 for LTX), so showing
# each for the duration it represents avoids a 4-8x fast-forward. Updates are
# held to at least one full playback pass so a swap can't truncate the motion.
_MIN_PASSES_BETWEEN_UPDATES = 1.1

# How a model family lays out its latent temporal axis. Index order is NOT
# always time order: MiniMax H3 stores [conditioning frame, then the rest in
# REVERSE], so walking 0..N plays everything after the first frame backwards.
# Verified by decoding a preview and comparing it frame-for-frame against the
# finished video: run a generation, decode a late preview, and compare its
# frames against the finished clip at matching timestamps. Do this per family
# before trusting a new one.
#   linear       : index order == time order (default assumption)
#   reverse_tail : frame 0 first, remaining frames reversed
_TEMPORAL_ORDER = {
    "MiniMaxH3Video": "reverse_tail",
    "MiniMaxH3AV": "reverse_tail",
}

# Early sampler steps can predict a near-uniform (black/grey) latent. Piping
# that to the UI blanks a preview that already had real content, and at ~8s a
# step it sits there for a long time. Skip degenerate frames and keep showing
# the last good one.
_MIN_FRAME_STDDEV = 12.0


def _stimma_extra_data(server) -> dict:
    """extra_data of the prompt currently executing here, or {}.

    Our executor tags its prompts (see comfy_client.queue_prompt); this is the
    only signal available in the sampling process, which is generally not the
    process hosting the STP server.
    """
    try:
        running = getattr(getattr(server, "prompt_queue", None), "currently_running", None)
        if not running:
            return {}
        item = next(iter(running.values()))
        extra = item[3] if len(item) > 3 else None
        return extra if isinstance(extra, dict) else {}
    except Exception:
        return {}


def _is_stimma_prompt(server) -> bool:
    return bool(_stimma_extra_data(server).get("stimma_preview"))


class _VideoAwarePreviewer:
    """Delegates to the stock previewer, additionally emitting an animated
    WebP for 5D latents. Any failure disables animation for the run and falls
    back to the stock single-frame behavior."""

    def __init__(self, inner, latent_format):
        self._inner = inner
        self._latent_format = latent_format
        self._rgb = None
        self._seq = next(_SEQ)
        self._min_interval = 1.5  # replaced once the clip length is known
        self._broken = False
        self._logged_skip = False

    def decode_latent_to_preview_image(self, preview_format, x0):
        if not self._broken and x0.ndim == 5 and x0.shape[2] > 1:
            try:
                self._emit_animation(x0)
            except Exception:
                self._broken = True
                logger.exception("Animated preview failed; falling back to single frame")
        result = self._inner.decode_latent_to_preview_image(preview_format, x0)
        # Raise the single-frame preview resolution for OUR prompts only. The
        # third element of the tuple is the max size ComfyUI downscales to, so
        # overriding it here is per-prompt — the alternative (bumping
        # latent_preview.MAX_PREVIEW_RESOLUTION) is process-global and would
        # silently make the user's own generations pay 4x the preview pixels.
        try:
            from server import PromptServer
            if len(result) == 3 and _is_stimma_prompt(PromptServer.instance):
                fmt, img, max_size = result
                return (fmt, img, max(max_size or 0, _STIMMA_PREVIEW_SIZE))
        except Exception:
            pass
        return result

    def _emit_animation(self, x0):
        import latent_preview
        from PIL import Image
        from server import PromptServer

        server = PromptServer.instance
        client_id = getattr(server, "client_id", None)
        if not client_id:
            logger.debug("animation skipped: no executing client on PromptServer")
            return

        # Only our own prompts get animated previews. The wrapper is installed
        # process-wide, so without this a video the user generates in ComfyUI's
        # own UI would pay the per-step decode + WebP encode and receive a
        # binary event its frontend discards.
        if not _is_stimma_prompt(server):
            return

        lf = self._latent_format
        if self._rgb is None:
            self._rgb = latent_preview.Latent2RGBPreviewer(
                lf.latent_rgb_factors,
                getattr(lf, "latent_rgb_factors_bias", None),
                getattr(lf, "latent_rgb_factors_reshape", None),
            )

        total = x0.shape[2]
        n = min(_MAX_FRAMES, total)
        if n > 1:
            idxs = [round(i * (total - 1) / (n - 1)) for i in range(n)]
        else:
            idxs = [0]

        # Map sample positions onto the family's real temporal order.
        order = _TEMPORAL_ORDER.get(type(lf).__name__, "linear")
        if order == "reverse_tail" and total > 2:
            timeline = [0] + list(range(total - 1, 0, -1))
            idxs = [timeline[i] for i in idxs]

        # Real-time playback: each shown frame stands for `ratio` real frames,
        # times the stride if the clip was subsampled to fit the budget.
        ratio = getattr(lf, "temporal_downscale_ratio", 1) or 1
        stride = (total - 1) / (n - 1) if n > 1 else 1
        # Real-time is the target, but a long clip's full pass would then take
        # many seconds and updates are gated on a full pass — so cap the frame
        # duration (mild speedup on long clips) to keep refinement visible.
        frame_ms = max(90, min(200, round(1000.0 * ratio * stride / _ASSUMED_FPS)))
        self._min_interval = max(
            1.2, (frame_ms * len(idxs) / 1000.0) * _MIN_PASSES_BETWEEN_UPDATES
        )

        # Claim the client's emit slot (see _claim): one sampler pass owns the
        # stream, and pacing is shared rather than per-instance.
        if not _claim(client_id, self._seq, self._min_interval):
            return

        frames = []
        size = None
        for t in idxs:
            # Keep the tensor 5D with the chosen frame first so the stock
            # previewer's 5D path (x0[0, :, 0]) selects it.
            img = self._rgb.decode_latent_to_preview(x0[:, :, t:t + 1])
            if size is None:
                w, h = img.size
                scale = max(1.0, _TARGET_WIDTH / max(1, w))
                size = (round(w * scale), round(h * scale))
            frames.append(img.resize(size, Image.BILINEAR))

        # Degenerate prediction (near-uniform)? Keep the previous preview.
        # Frame 0 is excluded deliberately: on i2v it is the conditioning
        # image, which looks fine even when every generated frame is still
        # black — sampling it would defeat the check entirely.
        try:
            from PIL import ImageStat
            n_f = len(frames)
            idxs = sorted({n_f // 4, n_f // 2, (3 * n_f) // 4} - {0}) or [1]
            probes = [frames[i] for i in idxs if i < n_f]
            if probes:
                # ImageStat is C-level; statistics.pstdev would do exact
                # Fraction arithmetic over ~170k Python ints per probe, on the
                # sampling process, every emit. Downscale first — a degenerate
                # frame is degenerate at any resolution.
                stds = [
                    ImageStat.Stat(f.convert("L").resize((32, 32))).stddev[0]
                    for f in probes
                ]
                _std = sum(stds) / len(stds)
                if _std < _MIN_FRAME_STDDEV:
                    logger.debug("skipping degenerate preview (stddev %.1f)", _std)
                    return
        except Exception:
            pass

        buf = io.BytesIO()
        # kmin/kmax = 1 makes EVERY frame a keyframe. Without it libwebp
        # inter-frame diffs: unchanged regions are encoded as transparent with
        # blend=yes, so each frame composites onto the previous canvas. That
        # is fine in theory, but the alpha plane is lossy here, so the
        # composite retains ghosts of earlier timepoints instead of replacing
        # them — frames smear together and trailing positions can dominate,
        # which is what made motion read as reversed/garbled. Full keyframes
        # cost bytes (a preview is ~100KB, still trivial) and are exact.
        frames[0].save(
            buf,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=[int(frame_ms)] * len(frames),
            loop=0,
            quality=70,
            method=4,
            lossless=False,
            allow_mixed=False,
            minimize_size=False,
            kmin=1,
            kmax=1,
        )
        server.send_sync(STIMMA_VIDEO_PREVIEW_EVENT, buf.getvalue(), client_id)
        logger.debug(
            "animated preview: seq=%s latent=%s frames=%s @%dms %dB",
            self._seq, tuple(x0.shape), len(frames), frame_ms, buf.getbuffer().nbytes,
        )


def install() -> None:
    """Wrap latent_preview.get_previewer. Idempotent."""
    import latent_preview

    if getattr(latent_preview, "_stimma_video_preview_installed", False):
        return
    orig = latent_preview.get_previewer

    def get_previewer(device, latent_format):
        previewer = orig(device, latent_format)
        if previewer is None:
            logger.info("get_previewer: no previewer for %s", type(latent_format).__name__)
            return None
        if getattr(latent_format, "latent_rgb_factors", None) is None:
            logger.info("get_previewer: no rgb factors for %s — animation off", type(latent_format).__name__)
            return previewer
        logger.info("get_previewer: wrapping %s for %s", type(previewer).__name__, type(latent_format).__name__)
        return _VideoAwarePreviewer(previewer, latent_format)

    latent_preview.get_previewer = get_previewer
    latent_preview._stimma_video_preview_installed = True
    logger.info("Installed animated video preview wrapper")
