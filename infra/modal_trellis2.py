"""Dedicated Modal deployment for batched TRELLIS.2 image-to-GLB jobs.

The public web function is deliberately CPU-only and short-lived: it spawns a
GPU FunctionCall and exposes a polling endpoint. Each GPU input gets its own
container, so a Stimma batch can fan out across H100/H200 capacity without
serialising ten high-resolution reconstructions on one device.
"""

from __future__ import annotations

import io
import os
import secrets
from pathlib import Path

import modal


APP_NAME = "stimma-trellis2"
MODEL_ROOT = Path("/models")
MODEL_VOLUME = modal.Volume.from_name("stimma-trellis2-models", create_if_missing=True)
TRELLIS_REVISION = os.environ.get("TRELLIS2_REVISION", "main")
HF_SECRET = modal.Secret.from_name("huggingface")

app = modal.App(APP_NAME)


download_image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install("fastapi[standard]", "python-multipart", "huggingface_hub>=0.27")
)


# CUDA 12.4 is the compatibility baseline documented by TRELLIS.2. H100 is
# intentional here: Modal may place the request on H200 at the same family
# level, while B200/B300 would require a separate CUDA 13.x compatibility pass.
trellis_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-devel-ubuntu22.04",
        add_python="3.10",
    )
    .entrypoint([])
    .apt_install(
        "build-essential",
        "curl",
        "git",
        "ninja-build",
        "libgl1",
        "libglib2.0-0",
        "libjpeg-dev",
    )
    .run_commands(
        "python -m pip install --upgrade pip",
        "python -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124",
        f"git clone --depth 1 --recursive --branch {TRELLIS_REVISION} https://github.com/microsoft/TRELLIS.2.git /opt/TRELLIS.2",
        # main currently predates the upstream Transformers 5.x DINOv3 fix;
        # copy the focused upstream source file without switching the whole
        # repo to an unmerged fork branch.
        "curl -fsSL https://raw.githubusercontent.com/microsoft/TRELLIS.2/3f4faad/trellis2/modules/image_feature_extractor.py -o /opt/TRELLIS.2/trellis2/modules/image_feature_extractor.py",
        "python -m pip install imageio imageio-ffmpeg tqdm easydict opencv-python-headless ninja trimesh transformers tensorboard pandas lpips zstandard kornia timm wheel psutil",
        "python -m pip install flash-attn==2.7.3 --no-build-isolation",
        "python -m pip install git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8",
        "git clone --recursive https://github.com/JeffreyXiang/CuMesh.git /tmp/CuMesh",
        "CC=gcc CXX=g++ TORCH_CUDA_ARCH_LIST=9.0 python -m pip install --no-build-isolation /tmp/CuMesh",
        "git clone --recursive https://github.com/JeffreyXiang/FlexGEMM.git /tmp/FlexGEMM",
        "CC=gcc CXX=g++ TORCH_CUDA_ARCH_LIST=9.0 python -m pip install --no-build-isolation /tmp/FlexGEMM",
        "CC=gcc CXX=g++ TORCH_CUDA_ARCH_LIST=9.0 python -m pip install --no-build-isolation /opt/TRELLIS.2/o-voxel",
        "git clone --depth 1 --branch v0.4.0 https://github.com/NVlabs/nvdiffrast.git /tmp/nvdiffrast",
        "CC=gcc CXX=g++ TORCH_CUDA_ARCH_LIST=9.0 python -m pip install --no-build-isolation /tmp/nvdiffrast",
    )
    .env(
        {
            "HF_HOME": str(MODEL_ROOT / "huggingface"),
            "TRANSFORMERS_CACHE": str(MODEL_ROOT / "huggingface"),
            "PYTHONPATH": "/opt/TRELLIS.2",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "TORCH_CUDA_ARCH_LIST": "9.0",
            "CC": "gcc",
            "CXX": "g++",
            "OPENCV_IO_ENABLE_OPENEXR": "1",
        }
    )
)


_PIPELINE = None


def _get_pipeline():
    global _PIPELINE
    if _PIPELINE is None:
        from trellis2.pipelines import Trellis2ImageTo3DPipeline

        _PIPELINE = Trellis2ImageTo3DPipeline.from_pretrained(
            "microsoft/TRELLIS.2-4B"
        )
        _PIPELINE.cuda()
    return _PIPELINE


@app.function(
    image=trellis_image,
    gpu="H100",
    volumes={MODEL_ROOT: MODEL_VOLUME},
    min_containers=0,
    max_containers=12,
    buffer_containers=0,
    scaledown_window=120,
    timeout=45 * 60,
    startup_timeout=30 * 60,
    memory=65536,
    retries=1,
    secrets=[HF_SECRET],
)
def generate_one(
    image_bytes: bytes,
    filename: str,
    resolution: str = "1536",
    texture_size: int = 4096,
    decimation_target: int = 1_000_000,
    seed: int | None = None,
) -> dict:
    """Generate one PBR GLB; Modal scales this Function horizontally per batch item."""
    import torch
    from PIL import Image
    import o_voxel

    pipeline = _get_pipeline()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    outputs, latents = pipeline.run(
        image,
        seed=seed if seed is not None else secrets.randbelow(2_147_483_647),
        preprocess_image=True,
        pipeline_type={
            "512": "512",
            "1024": "1024_cascade",
            "1536": "1536_cascade",
        }[resolution],
        return_latent=True,
    )
    # Decode from the latent representation used by the official TRELLIS.2
    # exporter so the GLB retains the full PBR attribute layout.
    shape_slat, tex_slat, latent_resolution = latents
    mesh = pipeline.decode_latent(shape_slat, tex_slat, latent_resolution)[0]
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices,
        faces=mesh.faces,
        attr_volume=mesh.attrs,
        coords=mesh.coords,
        attr_layout=pipeline.pbr_attr_layout,
        grid_size=latent_resolution,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=decimation_target,
        texture_size=texture_size,
        remesh=True,
        remesh_band=1,
        remesh_project=0,
        use_tqdm=False,
    )
    output_path = Path("/tmp") / f"{Path(filename).stem}-{secrets.token_hex(6)}.glb"
    glb.export(str(output_path), extension_webp=True)
    data = output_path.read_bytes()
    output_path.unlink(missing_ok=True)
    del outputs, latents, mesh, glb
    torch.cuda.empty_cache()
    return {"glb": data, "filename": f"{Path(filename).stem}.glb"}


@app.function(
    image=download_image,
    min_containers=0,
    max_containers=50,
    scaledown_window=30,
    memory=4096,
)
@modal.asgi_app(requires_proxy_auth=True)
def api():
    """Authenticated submit/result API used by Stimma's local backend."""
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import JSONResponse, Response

    web_app = FastAPI(title="Stimma TRELLIS.2")

    @web_app.get("/health")
    async def health():
        return {"status": "ok", "service": APP_NAME}

    @web_app.post("/v1/generate")
    async def submit(
        file: UploadFile = File(...),
        resolution: str = Form("1536"),
        texture_size: int = Form(4096),
        decimation_target: int = Form(1_000_000),
        seed: int | None = Form(None),
    ):
        if resolution not in {"512", "1024", "1536"}:
            raise HTTPException(status_code=400, detail="Unsupported resolution")
        if texture_size not in {1024, 2048, 4096}:
            raise HTTPException(status_code=400, detail="Unsupported texture size")
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Empty input image")
        call = generate_one.spawn(
            image_bytes,
            file.filename or "input.png",
            resolution,
            texture_size,
            decimation_target,
            seed,
        )
        return {"call_id": call.object_id, "status": "queued"}

    @web_app.get("/v1/result/{call_id}")
    async def result(call_id: str):
        try:
            call = modal.FunctionCall.from_id(call_id)
            value = call.get(timeout=0)
        except TimeoutError:
            return JSONResponse(status_code=202, content={"status": "processing"})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)[:500]) from exc

        if not isinstance(value, dict) or not isinstance(value.get("glb"), bytes):
            raise HTTPException(status_code=500, detail="TRELLIS.2 returned an invalid GLB")
        return Response(
            content=value["glb"],
            media_type="model/gltf-binary",
            headers={"Content-Disposition": f'attachment; filename="{value.get("filename", "asset.glb")}"'},
        )

    return web_app


@app.function(
    image=download_image,
    volumes={MODEL_ROOT: MODEL_VOLUME},
    timeout=2 * 60 * 60,
    secrets=[HF_SECRET],
)
def download_models() -> dict:
    """Warm the shared Volume so the first GPU container avoids a large download."""
    from huggingface_hub import snapshot_download

    paths = {
        "trellis": snapshot_download(
            repo_id="microsoft/TRELLIS.2-4B",
            cache_dir=MODEL_ROOT / "huggingface",
        )
    }
    # TRELLIS.2 uses a gated DINOv3 image encoder. When a Hugging Face
    # secret is attached, cache it here too so the first GPU call is warm.
    if os.environ.get("HF_TOKEN"):
        paths["dinov3"] = snapshot_download(
            repo_id="facebook/dinov3-vitl16-pretrain-lvd1689m",
            cache_dir=MODEL_ROOT / "huggingface",
        )
    MODEL_VOLUME.commit()
    return {"model_root": paths}


if __name__ == "__main__":
    print("Deploy with: modal deploy modal_trellis2.py")
