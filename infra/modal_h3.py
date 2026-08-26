"""Serverless MiniMax H3 and Music 3 ComfyUI deployment for Modal.

The GPU web server is protected by Modal proxy authentication and scales to
zero. A local authenticated bridge (modal_bridge.py) is the only intended
client.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import modal


APP_NAME = "comfyui-minimax-h3"
VOLUME_NAME = "comfyui-minimax-h3-models"
MODEL_ROOT = Path("/root/ComfyUI/models")

COMFYUI_REVISION = "0f1fa67ad8a68b62c65ebc97a7bf485df2459c3a"
STIMMA_REVISION = "a301a1f3f411a1cd10327b888398c5835078c22c"
TURBO_NODE_REVISION = "4274783a23afcfdbea3b4876cb79effd6c510785"
H3_REVISION = "d07f69bc8fa09c9717e1e47180034f9322e0e54d"
TURBO_REVISION = "43a74557ac3f6539db8e0f2a959d03feb7a81480"
MUSIC_REVISION = "6332b49584554162b85fd71f2a4cdd8eeb1fc42d"

H3_FILES = (
    "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
    "vae/minimax_h3_video_vae_fp16.safetensors",
)
H3_FULL_BF16_FILES = (
    # Full, unpruned BF16 checkpoints for the dedicated B300 HD worker.
    # H3's full-precision public checkpoints are BF16 (the VAE remains FP16
    # and the audio VAE remains FP32); there is no separate H3 FP16 checkpoint.
    "diffusion_models/minimax_h3_fl2va_bf16.safetensors",
    "diffusion_models/minimax_h3_ref2va_bf16.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors",
)
TURBO_FILE = "minimax_h3_turbo_v4_step600_ema.safetensors"
MUSIC_FILES = (
    "diffusion_models/minimax_music3_dit_int8_convrot.safetensors",
    "text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
    "vae/minimax_music3_dav.safetensors",
)

app = modal.App(APP_NAME)
models = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True, version=2)
HF_SECRET = modal.Secret.from_name("huggingface")

download_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("huggingface_hub[hf_xet]>=1.0,<2")
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)

ROOT_DIR = Path(__file__).resolve().parent

comfy_image = (
    modal.Image.from_registry(
        # B300 requires CUDA 13.1+; the RTX PRO 6000 remains supported by the
        # same Blackwell image.
        "nvidia/cuda:13.1.1-devel-ubuntu24.04",
        add_python="3.12",
    )
    .entrypoint([])
    .apt_install("build-essential", "ffmpeg", "git", "ninja-build")
    .run_commands(
        "git clone https://github.com/Comfy-Org/ComfyUI.git /root/ComfyUI",
        f"git -C /root/ComfyUI checkout {COMFYUI_REVISION}",
        "git clone https://github.com/stimma-ai/ComfyUI-Stimma.git "
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma",
        f"git -C /root/ComfyUI/custom_nodes/ComfyUI-Stimma checkout {STIMMA_REVISION}",
        "git clone https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo.git "
        "/root/ComfyUI/custom_nodes/ComfyUI-MiniMax-H3-Turbo",
        "git -C /root/ComfyUI/custom_nodes/ComfyUI-MiniMax-H3-Turbo checkout "
        f"{TURBO_NODE_REVISION}",
        # The pinned Stimma workflows still name the first-generation Turbo
        # checkpoint.  Keep their graph wiring, but select the current v4-600
        # EMA checkpoint recommended for static and slow architectural motion.
        "sed -i 's/minimax_h3_turbo_4step_ema_ckpt850.safetensors/"
        "minimax_h3_turbo_v4_step600_ema.safetensors/g' "
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/workflows/"
        "Stimma-MiniMax-H3-*-Turbo.json",
        "python -m pip install --upgrade pip",
        "python -m pip install -r /root/ComfyUI/requirements.txt",
        "python -m pip install -r "
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/requirements.txt",
        # MiniMax H3's workflow-scoped attention node imports the CUDA FP8
        # SageAttention API. Build the pinned release in this image instead
        # of using a prebuilt wheel: ComfyUI's current requirements resolve
        # to PyTorch 2.13, while the public Comfy-Org wheel is built against
        # an older PyTorch ABI and fails at import time with an undefined
        # c10 symbol.
        "git clone --depth 1 --branch v2.2.0 https://github.com/thu-ml/SageAttention.git /tmp/SageAttention",
        # Image builds do not expose a GPU. Compile SageAttention for both
        # Blackwell families used by this app: B300 (SM 10.3) and RTX PRO
        # 6000 (SM 12.0).
        "TORCH_CUDA_ARCH_LIST='10.3;12.0' MAX_JOBS=4 CC=gcc CXX=g++ python -m pip install --no-build-isolation /tmp/SageAttention",
        # Modal Volumes may only mount over an absent or empty image path.
        # ComfyUI ships placeholder files under models/, so remove that copy;
        # the persistent Volume becomes the complete models directory at run time.
        "rm -rf /root/ComfyUI/models",
    )
    # The local Stimma plugin adds the audio output node and the Music 3
    # workflow. Keep the remote image pinned for H3, but overlay these small
    # integration files so both tools use the same authenticated bridge.
    .add_local_file(
        str(ROOT_DIR / "ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/outputs.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/outputs.py",
        copy=True,
    )
    .add_local_file(
        str(ROOT_DIR / "ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/__init__.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/__init__.py",
        copy=True,
    )
    .add_local_file(
        str(ROOT_DIR / "ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/minimax_h3_sage.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/minimax_h3_sage.py",
        copy=True,
    )
    .add_local_file(
        str(ROOT_DIR / "ComfyUI/custom_nodes/ComfyUI-Stimma/stp_server/discovery.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/stp_server/discovery.py",
        copy=True,
    )
    .add_local_file(
        str(ROOT_DIR / "ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/fields.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/fields.py",
        copy=True,
    )
    .add_local_file(
        str(ROOT_DIR / "ComfyUI/custom_nodes/ComfyUI-Stimma/workflows/Stimma-MiniMax-Music3-T2A.json"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/workflows/Stimma-MiniMax-Music3-T2A.json",
        copy=True,
    )
)


@app.function(
    image=download_image,
    volumes={MODEL_ROOT: models},
    cpu=4,
    memory=8192,
    timeout=2 * 60 * 60,
    secrets=[HF_SECRET],
)
def download_models(include_reference: bool = True, include_turbo: bool = True) -> dict:
    """Download H3 weights directly into the persistent Modal Volume."""
    from huggingface_hub import hf_hub_download

    selected = list(H3_FILES)
    if not include_reference:
        selected.remove(
            "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors"
        )

    downloaded = []
    for filename in selected:
        hf_hub_download(
            repo_id="Comfy-Org/MiniMax-H3",
            filename=filename,
            revision=H3_REVISION,
            local_dir=MODEL_ROOT,
        )
        downloaded.append(filename)

    if include_turbo:
        lora_dir = MODEL_ROOT / "loras"
        lora_dir.mkdir(parents=True, exist_ok=True)
        hf_hub_download(
            repo_id="larryvrh/MiniMax-H3-Turbo-Lora",
            filename=TURBO_FILE,
            revision=TURBO_REVISION,
            local_dir=lora_dir,
        )
        old_turbo = lora_dir / "minimax-h3" / TURBO_FILE
        if old_turbo.exists():
            old_turbo.unlink()
            try:
                old_turbo.parent.rmdir()
            except OSError:
                pass
        downloaded.append(f"loras/{TURBO_FILE}")

    models.commit()
    return {"downloaded": downloaded, "model_root": str(MODEL_ROOT)}


@app.function(
    image=download_image,
    volumes={MODEL_ROOT: models},
    cpu=4,
    memory=8192,
    timeout=4 * 60 * 60,
    secrets=[HF_SECRET],
)
def download_hd_models() -> dict:
    """Download the full BF16 H3 weights used by the B300 HD worker."""
    from huggingface_hub import hf_hub_download

    downloaded = []
    for filename in H3_FULL_BF16_FILES:
        hf_hub_download(
            repo_id="Comfy-Org/MiniMax-H3",
            filename=filename,
            revision=H3_REVISION,
            local_dir=MODEL_ROOT,
        )
        downloaded.append(filename)

    models.commit()
    return {"downloaded": downloaded, "model_root": str(MODEL_ROOT)}


@app.function(
    image=download_image,
    volumes={MODEL_ROOT: models},
    cpu=4,
    memory=8192,
    timeout=2 * 60 * 60,
    secrets=[HF_SECRET],
)
def download_music_models() -> dict:
    """Download MiniMax Music 3 weights into the shared Modal Volume."""
    from huggingface_hub import hf_hub_download

    downloaded = []
    for filename in MUSIC_FILES:
        hf_hub_download(
            repo_id="Comfy-Org/MiniMax-Music-3",
            filename=filename,
            revision=MUSIC_REVISION,
            local_dir=MODEL_ROOT,
        )
        downloaded.append(filename)

    models.commit()
    return {"downloaded": downloaded, "model_root": str(MODEL_ROOT)}


@app.function(
    image=comfy_image,
    gpu="RTX-PRO-6000",
    volumes={MODEL_ROOT: models},
    min_containers=0,
    max_containers=1,
    buffer_containers=0,
    scaledown_window=2,
    timeout=60 * 60,
    startup_timeout=20 * 60,
    memory=32768,
)
@modal.concurrent(max_inputs=32)
@modal.web_server(
    8188,
    startup_timeout=20 * 60,
    requires_proxy_auth=True,
)
def comfyui() -> None:
    """Start one authenticated ComfyUI server on a 96 GB RTX PRO 6000."""
    subprocess.Popen(
        [
            "python",
            "main.py",
            "--listen",
            "0.0.0.0",
            "--port",
            "8188",
            "--disable-auto-launch",
            "--preview-method",
            "none",
        ],
        cwd="/root/ComfyUI",
    )


@app.function(
    image=comfy_image,
    gpu="B300",
    volumes={MODEL_ROOT: models},
    min_containers=0,
    max_containers=1,
    buffer_containers=0,
    scaledown_window=2,
    timeout=2 * 60 * 60,
    startup_timeout=30 * 60,
    # Full BF16 H3 includes the unpruned diffusion model and 32B BF16 text
    # encoder. Give the B300 worker enough host RAM for load/offload spikes.
    memory=131072,
)
# One H3 job needs a live progress WebSocket and concurrent HTTP calls
# (/prompt, /history, /view). A single Modal input slot deadlocks that pair:
# the WebSocket occupies the slot while /prompt waits forever. The local STP
# provider serializes HD jobs, so two slots are enough without enabling
# concurrent B300 generations.
@modal.concurrent(max_inputs=2)
@modal.web_server(
    8188,
    startup_timeout=30 * 60,
    requires_proxy_auth=True,
)
def comfyui_hd() -> None:
    """Start the dedicated B300 full-BF16 worker for HD H3 generations."""
    subprocess.Popen(
        [
            "python",
            "main.py",
            "--listen",
            "0.0.0.0",
            "--port",
            "8188",
            "--disable-auto-launch",
            "--preview-method",
            "none",
        ],
        cwd="/root/ComfyUI",
    )


@app.function(image=download_image, volumes={MODEL_ROOT: models}, timeout=10 * 60)
def model_inventory() -> list[dict]:
    """Return paths and byte sizes without allocating a GPU."""
    inventory = []
    if MODEL_ROOT.exists():
        for path in sorted(MODEL_ROOT.rglob("*.safetensors")):
            inventory.append(
                {"path": str(path.relative_to(MODEL_ROOT)), "bytes": path.stat().st_size}
            )
    return inventory
