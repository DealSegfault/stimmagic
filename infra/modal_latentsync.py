"""Scale-to-zero LatentSync 1.6 service for Maya's dialogue shots.

This app is intentionally separate from the MiniMax H3 ComfyUI image: its
dependencies and checkpoints cannot make H3 cold starts slower, and the GPU is
released two seconds after each lip-sync call.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import modal


APP_NAME = "maya-latentsync"
REPOSITORY_REVISION = "a229c3948406bc2cf6eaf4873e662e70c6a04746"
REPOSITORY = Path("/root/LatentSync")
CHECKPOINTS = REPOSITORY / "checkpoints"
HF_CACHE = Path("/root/.cache/huggingface")

app = modal.App(APP_NAME)
checkpoints = modal.Volume.from_name("maya-latentsync-checkpoints", create_if_missing=True, version=2)
hf_cache = modal.Volume.from_name("maya-latentsync-hf-cache", create_if_missing=True, version=2)

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04",
        add_python="3.10",
    )
    .entrypoint([])
    .apt_install(
        "build-essential",
        "clang",
        "ffmpeg",
        "git",
        "libgl1",
        "libglib2.0-0",
    )
    .run_commands(
        "git clone https://github.com/bytedance/LatentSync.git /root/LatentSync",
        f"git -C /root/LatentSync checkout {REPOSITORY_REVISION}",
        "python -m pip install --upgrade pip wheel setuptools",
        "python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128",
        "python -m pip install "
        "diffusers==0.32.2 transformers==4.48.0 decord==0.6.0 "
        "accelerate==0.26.1 einops==0.7.0 omegaconf==2.3.0 "
        "opencv-python==4.9.0.80 mediapipe==0.10.11 "
        "python_speech_features==0.6 librosa==0.10.1 scenedetect==0.6.1 "
        "ffmpeg-python==0.2.0 imageio==2.31.1 imageio-ffmpeg==0.5.1 "
        "lpips==0.1.4 face-alignment==1.4.1 huggingface-hub==0.30.2 "
        "numpy==1.26.4 kornia==0.8.0 insightface==0.7.3 "
        "onnxruntime-gpu==1.21.0 DeepCache==0.1.1",
    )
)


def _ensure_models() -> None:
    from huggingface_hub import hf_hub_download

    for filename in ("latentsync_unet.pt", "whisper/tiny.pt"):
        hf_hub_download(
            repo_id="ByteDance/LatentSync-1.6",
            filename=filename,
            local_dir=CHECKPOINTS,
            cache_dir=HF_CACHE,
        )
    checkpoints.commit()
    hf_cache.commit()


@app.function(
    image=image,
    volumes={CHECKPOINTS: checkpoints, HF_CACHE: hf_cache},
    cpu=4,
    memory=16384,
    timeout=30 * 60,
)
def download_models() -> dict:
    """Populate persistent weights without allocating a GPU."""
    _ensure_models()
    return {
        "checkpoint": str(CHECKPOINTS / "latentsync_unet.pt"),
        "whisper": str(CHECKPOINTS / "whisper/tiny.pt"),
    }


@app.function(
    image=image,
    gpu="RTX-PRO-6000",
    volumes={CHECKPOINTS: checkpoints, HF_CACHE: hf_cache},
    min_containers=0,
    max_containers=1,
    buffer_containers=0,
    scaledown_window=2,
    timeout=30 * 60,
    startup_timeout=15 * 60,
    memory=32768,
)
def lipsync(
    video_bytes: bytes,
    audio_bytes: bytes,
    inference_steps: int = 30,
    guidance_scale: float = 1.5,
    seed: int = 4200108,
) -> bytes:
    """Return an H.264 MP4 with LatentSync 1.6 mouth motion and supplied audio."""
    _ensure_models()
    with tempfile.TemporaryDirectory(prefix="maya-lipsync-") as temp_dir:
        temp = Path(temp_dir)
        source_video = temp / "source.mp4"
        source_audio = temp / "maya.wav"
        output_video = temp / "maya_lipsync.mp4"
        source_video.write_bytes(video_bytes)
        source_audio.write_bytes(audio_bytes)

        subprocess.run(
            [
                "python",
                "-m",
                "scripts.inference",
                "--unet_config_path",
                "configs/unet/stage2_512.yaml",
                "--inference_ckpt_path",
                "checkpoints/latentsync_unet.pt",
                "--inference_steps",
                str(inference_steps),
                "--guidance_scale",
                str(guidance_scale),
                "--video_path",
                str(source_video),
                "--audio_path",
                str(source_audio),
                "--video_out_path",
                str(output_video),
                "--temp_dir",
                str(temp / "work"),
                "--seed",
                str(seed),
            ],
            cwd=REPOSITORY,
            check=True,
        )
        return output_video.read_bytes()
