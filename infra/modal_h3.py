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

COMFYUI_REVISION = "b0b743566f65daafc423b4fea8a2fbda94b3384a"  # ComfyUI v0.39.0, native Sol attention
STIMMA_REVISION = "a301a1f3f411a1cd10327b888398c5835078c22c"
TURBO_NODE_REVISION = "4274783a23afcfdbea3b4876cb79effd6c510785"
H3_REVISION = "d07f69bc8fa09c9717e1e47180034f9322e0e54d"
TURBO_REVISION = "3ec17a324ced54151364f24f8b5fb6bf7e26414f"
MUSIC_REVISION = "6332b49584554162b85fd71f2a4cdd8eeb1fc42d"

H3_FILES = (
    "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
    "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "diffusion_models/minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
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
TURBO_FILES = (
    "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors",
    "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors",
)
MUSIC_FILES = (
    "diffusion_models/minimax_music3_dit_int8_convrot.safetensors",
    "text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
    "vae/minimax_music3_dav.safetensors",
)

app = modal.App(APP_NAME)
models = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True, version=2)

download_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("huggingface_hub[hf_xet]>=1.0,<2")
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-Stimma"

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
        "python -m pip install --upgrade pip",
        "python -m pip install -r /root/ComfyUI/requirements.txt",
        "python -m pip install -r "
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/requirements.txt",
        # MiniMax H3's workflow-scoped attention node imports the CUDA FP8
        # SageAttention API. Build the pinned release in this image instead
        # of using a prebuilt wheel: ComfyUI leaves PyTorch unpinned, while
        # the public Comfy-Org wheel can target an older ABI and fail at
        # import time with an undefined c10 symbol.
        "git clone --depth 1 --branch v2.2.0 https://github.com/thu-ml/SageAttention.git /tmp/SageAttention",
        # PyTorch 2.14 requires C++20, while SageAttention 2.2.0 still pins
        # C++17 in setup.py.
        "sed -i 's/-std=c++17/-std=c++20/g' /tmp/SageAttention/setup.py",
        # Image builds do not expose a GPU. Compile SageAttention for both
        # Blackwell families used by this app: B300 (SM 10.3) and RTX PRO
        # 6000 (SM 12.0).
        "TORCH_CUDA_ARCH_LIST='10.3;12.0' MAX_JOBS=4 CC=gcc CXX=g++ python -m pip install --no-build-isolation /tmp/SageAttention",
        # FlashAttention-4 is the Blackwell-native CuTeDSL path used by the
        # workflow-scoped H3 B300 adapter below.
        "git clone --depth 1 https://github.com/Dao-AILab/flash-attention.git /tmp/flash-attention",
        "python -m pip install --no-build-isolation '/tmp/flash-attention/flash_attn/cute[cu13]'",
        # Modal Volumes may only mount over an absent or empty image path.
        # ComfyUI ships placeholder files under models/, so remove that copy;
        # the persistent Volume becomes the complete models directory at run time.
        "rm -rf /root/ComfyUI/models",
    )
    # The local Stimma plugin adds the audio output node and the Music 3
    # workflow. Keep the remote image pinned for H3, but overlay these small
    # integration files so both tools use the same authenticated bridge.
    .add_local_file(
        str(PLUGIN_ROOT / "nodes/outputs.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/outputs.py",
        copy=True,
    )
    .add_local_file(
        str(PLUGIN_ROOT / "nodes/__init__.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/__init__.py",
        copy=True,
    )
    .add_local_file(
        str(PLUGIN_ROOT / "nodes/image_crop.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/image_crop.py",
        copy=True,
    )
    .add_local_file(
        str(PLUGIN_ROOT / "nodes/minimax_h3_sage.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/minimax_h3_sage.py",
        copy=True,
    )
    .add_local_file(
        str(PLUGIN_ROOT / "stp_server/discovery.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/stp_server/discovery.py",
        copy=True,
    )
    .add_local_file(
        str(PLUGIN_ROOT / "nodes/fields.py"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/nodes/fields.py",
        copy=True,
    )
    .add_local_file(
        str(PLUGIN_ROOT / "workflows/Stimma-MiniMax-Music3-T2A.json"),
        "/root/ComfyUI/custom_nodes/ComfyUI-Stimma/workflows/Stimma-MiniMax-Music3-T2A.json",
        copy=True,
    )
)

# Keep the locally served Turbo graphs identical to those deployed on Modal.
for mode in ("I2V", "T2V", "R2V"):
    workflow_name = f"Stimma-MiniMax-H3-{mode}-Turbo.json"
    comfy_image = comfy_image.add_local_file(
        str(PLUGIN_ROOT / "workflows" / workflow_name),
        f"/root/ComfyUI/custom_nodes/ComfyUI-Stimma/workflows/{workflow_name}",
        copy=True,
    )


@app.function(
    image=download_image,
    volumes={MODEL_ROOT: models},
    cpu=4,
    memory=8192,
    timeout=2 * 60 * 60,
)
def download_models(include_reference: bool = True, include_turbo: bool = True) -> dict:
    """Download H3 weights directly into the persistent Modal Volume."""
    from huggingface_hub import hf_hub_download

    selected = list(H3_FILES)
    if not include_reference:
        selected = [filename for filename in selected if "minimax_h3_ref2va" not in filename]

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
        for filename in TURBO_FILES if include_reference else TURBO_FILES[:1]:
            hf_hub_download(
                repo_id="lightx2v/Minimax-h3-Turbo",
                filename=filename,
                revision=TURBO_REVISION,
                local_dir=lora_dir,
            )
            downloaded.append(f"loras/{filename}")

    models.commit()
    return {"downloaded": downloaded, "model_root": str(MODEL_ROOT)}


@app.function(
    image=download_image,
    volumes={MODEL_ROOT: models},
    cpu=4,
    memory=8192,
    timeout=4 * 60 * 60,
)
def download_hd_models() -> dict:
    """Download the HD H3 weights used by the B300 worker."""
    from huggingface_hub import hf_hub_download

    downloaded = []
    # Keep both choices on the HD volume: FP8 is the practical automatic
    # route, while BF16 (Full) remains available for explicit quality runs.
    selected = list(H3_FULL_BF16_FILES) + [
        "diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
        "diffusion_models/minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
        "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "vae/minimax_h3_video_vae_fp16.safetensors",
        "vae/minimax_h3_audio_vae_fp32.safetensors",
    ]
    for filename in selected:
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
    # Standalone jobs release quickly. Prepared series hold a scoped WebSocket
    # instead of changing this global idle shutdown setting.
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
# A prepared series adds one scoped warm-hold WebSocket alongside the
# job's progress WebSocket and HTTP calls (/prompt, /history, /view).
# Three request slots avoid deadlocks; the local STP pool still serializes
# B300 generations. This does not change scale-to-zero or GPU concurrency.
@modal.concurrent(max_inputs=3)
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
