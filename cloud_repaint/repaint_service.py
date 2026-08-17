"""Modal endpoint for Stimma's cloud-only FLUX.1 Fill repaint.

Weights are downloaded once into a persistent Modal Volume (like H3) and
mounted by the L40S inference workers. Runtime inference has no Hugging Face
credential or network dependency.
"""

import asyncio
import base64
import io
import os
import time
from typing import Any

import modal

MODEL_ID = "black-forest-labs/FLUX.1-Fill-dev"
MODEL_ROOT = "/models"
MODEL_DIR = f"{MODEL_ROOT}/FLUX.1-Fill-dev"
VOLUME_NAME = "stimma-flux-fill-models"

app = modal.App("stimma-flux-fill")
models = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
runtime_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.5.1", "diffusers==0.32.2", "transformers==4.48.3",
        "accelerate==1.3.0", "safetensors", "huggingface_hub", "pillow", "fastapi",
        "sentencepiece", "protobuf",
    )
)
download_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "huggingface_hub[hf_xet]>=0.27,<1"
)
# Credential is scoped to the one-time volume bootstrap only.
hf = modal.Secret.from_name("huggingface", required_keys=["HF_TOKEN"])


@app.function(image=download_image, volumes={MODEL_ROOT: models}, cpu=4, memory=8192,
              timeout=2 * 60 * 60, secrets=[hf])
def download_models(force: bool = False) -> dict[str, Any]:
    """Populate the persistent Modal Volume with FLUX Fill weights once."""
    from pathlib import Path
    from huggingface_hub import snapshot_download

    marker = Path(MODEL_DIR) / "model_index.json"
    if marker.exists() and not force:
        return {"status": "ready", "model": MODEL_ID, "volume": VOLUME_NAME,
                "model_dir": MODEL_DIR, "downloaded": False}
    snapshot_download(repo_id=MODEL_ID, local_dir=MODEL_DIR,
                      token=os.environ["HF_TOKEN"])
    models.commit()
    return {"status": "ready", "model": MODEL_ID, "volume": VOLUME_NAME,
            "model_dir": MODEL_DIR, "downloaded": True}


def _decode(value: str, mode: str = "RGB"):
    from PIL import Image
    encoded = value.split(",", 1)[1] if value.startswith("data:") else value
    return Image.open(io.BytesIO(base64.b64decode(encoded))).convert(mode)


@app.cls(image=runtime_image, gpu="L40S", volumes={MODEL_ROOT: models},
         timeout=600, scaledown_window=180)
class FluxFill:
    @modal.enter()
    def load(self):
        import torch
        from diffusers import FluxFillPipeline
        self.torch = torch
        self.pipe = FluxFillPipeline.from_pretrained(
            MODEL_DIR, torch_dtype=torch.bfloat16, local_files_only=True)
        self.pipe.to("cuda")

    @modal.method()
    def generate(self, source_image: str, mask_image: str, prompt: str,
                 seed: int | None, steps: int, guidance: float) -> dict[str, Any]:
        from PIL import ImageOps
        source, mask = _decode(source_image), _decode(mask_image, "L")
        if source.size != mask.size:
            mask = mask.resize(source.size)
        if mask.getbbox() is None:
            return {"error": {"code": "invalid_mask", "message": "Le masque est vide."}}
        scale = min(1, 1536 / max(source.size))
        size = (max(64, int(source.width * scale) // 16 * 16),
                max(64, int(source.height * scale) // 16 * 16))
        source, mask = ImageOps.fit(source, size), ImageOps.fit(mask, size)
        actual_seed = seed if seed is not None else int(time.time_ns() % 2147483647)
        started = time.perf_counter()
        generator = self.torch.Generator(device="cuda").manual_seed(actual_seed)
        result = self.pipe(prompt=prompt, image=source, mask_image=mask,
                           num_inference_steps=steps, guidance_scale=guidance,
                           generator=generator).images[0]
        buffer = io.BytesIO()
        result.save(buffer, "PNG")
        seconds = round(time.perf_counter() - started, 2)
        rate = float(os.environ.get("STIMMA_REPAINT_GPU_USD_PER_SEC", "0"))
        return {"status": "completed", "output": {"image": "data:image/png;base64," +
                base64.b64encode(buffer.getvalue()).decode()},
                "metadata": {"model": MODEL_ID, "provider": "Modal", "gpu": "L40S",
                "gpuMemoryGb": 48, "gpuSeconds": seconds,
                "estimatedCostUsd": round(seconds * rate, 4) if rate else None,
                "seed": actual_seed, "steps": steps, "guidance": guidance}}


@app.function(timeout=620)
def run_repaint(payload):
    return FluxFill().generate.remote(payload["sourceImage"], payload["maskImage"],
                                       payload["prompt"], payload.get("seed"),
                                       int(payload.get("steps", 28)),
                                       float(payload.get("guidance", 30)))


@app.function(image=runtime_image, volumes={MODEL_ROOT: models})
@modal.asgi_app(requires_proxy_auth=True)
def api():
    from pathlib import Path
    from fastapi import FastAPI, Request
    service = FastAPI()

    @service.get("/health")
    async def health():
        ready = Path(MODEL_DIR, "model_index.json").exists()
        return {"status": "ready" if ready else "model_not_ready", "model": MODEL_ID, "gpu": "L40S"}

    @service.post("/jobs")
    async def create(payload: dict, request: Request):
        if not Path(MODEL_DIR, "model_index.json").exists():
            return {"error": {"code": "model_not_ready", "message": "Préparez le volume Modal avec download_models avant l'inférence."}}
        if not payload.get("sourceImage") or not payload.get("maskImage") or not str(payload.get("prompt", "")).strip():
            return {"error": {"code": "invalid_repaint_request", "message": "Image, masque et prompt requis."}}
        call = run_repaint.spawn(payload)
        return {"id": call.object_id, "status": "queued", "provider": "Modal", "model": MODEL_ID, "gpu": "L40S", "pollAfterMs": 2500}

    @service.get("/jobs/{job_id}")
    async def poll(job_id: str, request: Request):
        try:
            result = await modal.FunctionCall.from_id(job_id).get.aio(timeout=0.1)
            return {"id": job_id, **result}
        except (TimeoutError, asyncio.TimeoutError):
            return {"id": job_id, "status": "running", "pollAfterMs": 2500}
        except Exception as exc:
            return {"id": job_id, "status": "failed", "error": {"code": "generation_failed", "message": str(exc)}}
    return service
