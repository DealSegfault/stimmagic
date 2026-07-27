#!/usr/bin/env python3
"""Patch-composite viability harness for the op-stack image editor.

The editor's *patch* op class composites a generative result client-side: it takes
only the pixels inside the mask and draws them over its own input through a
feathered mask. That is only sound when a tool's output is **geometrically
registered** with its input — same dimensions, no global shift, no rescale. Tools
that fail registration cannot be patch-class and must run as whole-image
checkpoints instead.

This harness answers that question per tool with real provider runs. For each
inpaint tool it submits a fixed image + fixed mask, then measures the returned
image against the input *outside* the mask.

Registration decides the verdict:

  dims        output dimensions == input dimensions
  shift       the outside-mask region is split into 64px tiles and each is
              aligned independently in a +/-16px search. Tiles the model
              repainted are dropped by a correlation gate; the survivors vote.
              The winning offset must be (0, 0) with >=90% agreement. Voting is
              necessary because inpaint models routinely paint content well
              outside the mask, which a whole-frame correlation cannot survive.
  quadrants   the same votes tallied per corner. A uniform rescale keeps the
              centre registered while pushing opposite corners apart, so this
              catches scale changes the global vote would average away.

Verdict is `patch` when dims match and the tiles agree on (0, 0), `whole-image`
when registration fails, and `inconclusive` when too few tiles survive to tell.

Preservation is measured but does NOT decide the verdict, because the patch
composite discards every pixel outside the mask by construction — a tool that
repaints the whole frame is still patch-eligible, it just throws that work away.
What it predicts is how the composite will *look*:

  far field   absolute-difference statistics well away from the mask. Near zero
              means the tool crops-and-stitches; large means it round-trips or
              reinterprets the whole frame.
  near ring   the same statistics in a band just outside the mask — the region
              the feathered composite actually blends against.
  spill       percentage of outside-mask pixels the model changed materially.
              High spill means the composite will visibly clip the model's
              intent (a painted hand or shadow chopped at the mask edge), which
              is a signal to grow the mask, not a defect in the tool.

Usage (from the backend directory, which owns the Python environment):

    cd backend
    uv run python ../scripts/patch_composite_harness.py \
        --base-url http://127.0.0.1:9191 --profile profile-XXXX

Outputs a JSON report and per-tool PNGs (input, mask, output, difference map)
into --out-dir for eyeballing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw


DEFAULT_PROMPT = "a small potted plant"
INPAINT_TASK_TYPE = "inpaint-image"

# Registration thresholds. A tool qualifies for the patch class when enough
# untouched tiles survive the confidence gate and they overwhelmingly agree the
# output sits at offset (0, 0).
MIN_CONFIDENT_TILES = 12
MIN_SHIFT_AGREEMENT = 0.9
MIN_QUADRANT_TILES = 4
MIN_QUADRANT_AGREEMENT = 0.6
MIN_TILE_STD = 12.0
MIN_TILE_CORR = 0.9
MIN_PEAK_MARGIN = 0.05


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def build_test_card(width: int, height: int) -> Image.Image:
    """A deterministic, high-frequency test card.

    Fine structure is deliberate: a resize or half-pixel shift destroys thin
    lines far more visibly than it does smooth gradients, so registration
    failures show up in the statistics instead of hiding under a low mean error.
    """
    rng = np.random.default_rng(0x5713)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)

    r = (xx / max(width - 1, 1)) * 255.0
    g = (yy / max(height - 1, 1)) * 255.0
    b = np.full((height, width), 128.0, dtype=np.float32)

    # 1px checker: the first thing any resample smears.
    checker = (((xx.astype(np.int32) // 1) + (yy.astype(np.int32) // 1)) % 2) * 40.0
    # Concentric rings: sensitive to scale changes.
    cx, cy = width / 2.0, height / 2.0
    rings = np.sin(np.hypot(xx - cx, yy - cy) / 3.0) * 40.0
    noise = rng.integers(0, 24, size=(height, width)).astype(np.float32)

    arr = np.stack([r + checker + noise, g + rings + noise, b + checker + rings], axis=-1)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")

    draw = ImageDraw.Draw(img)
    for i in range(0, width, 64):
        draw.line([(i, 0), (i, height)], fill=(255, 255, 255), width=1)
    for i in range(0, height, 64):
        draw.line([(0, i), (width, i)], fill=(0, 0, 0), width=1)
    return img


def build_mask(width: int, height: int) -> Image.Image:
    """White ellipse over roughly the central 15% of the frame; black elsewhere."""
    mask = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(mask)
    rx, ry = width * 0.22, height * 0.22
    cx, cy = width / 2.0, height / 2.0
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(255, 255, 255))
    return mask


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------

@dataclass
class Measurement:
    dims_match: bool
    input_dims: tuple[int, int]
    output_dims: tuple[int, int]
    best_shift: tuple[int, int] | None = None
    shift_agreement: float | None = None
    candidate_tiles: int = 0
    confident_tiles: int = 0
    repaint_pct: float | None = None
    shift_votes: dict[str, int] = field(default_factory=dict)
    quadrant_shifts: dict[str, list[int]] = field(default_factory=dict)
    far_field: dict[str, float] = field(default_factory=dict)
    near_ring: dict[str, float] = field(default_factory=dict)
    spill_pct: float | None = None


_QUADRANTS = {
    "top_left": lambda cy, cx, ih, iw: cy < ih / 2 and cx < iw / 2,
    "top_right": lambda cy, cx, ih, iw: cy < ih / 2 and cx >= iw / 2,
    "bottom_left": lambda cy, cx, ih, iw: cy >= ih / 2 and cx < iw / 2,
    "bottom_right": lambda cy, cx, ih, iw: cy >= ih / 2 and cx >= iw / 2,
}


def _gray(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float32)


def _ncc(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> float:
    """Normalised cross-correlation over the valid pixels only."""
    av = a[valid]
    bv = b[valid]
    if av.size == 0:
        return float("nan")
    av = av - av.mean()
    bv = bv - bv.mean()
    denom = float(np.sqrt((av * av).sum() * (bv * bv).sum()))
    if denom == 0.0:
        return float("nan")
    return float((av * bv).sum() / denom)


def _stats(delta: np.ndarray) -> dict[str, float]:
    if delta.size == 0:
        return {}
    return {
        "mean_abs": round(float(delta.mean()), 3),
        "p99_abs": round(float(np.percentile(delta, 99)), 1),
        "max_abs": round(float(delta.max()), 1),
        "pct_over_2": round(float((delta > 2).mean() * 100.0), 2),
        "pct_over_8": round(float((delta > 8).mean() * 100.0), 2),
        "pct_over_16": round(float((delta > 16).mean() * 100.0), 2),
        "pixels": int(delta.size),
    }


def _best_shift(
    gi: np.ndarray, go: np.ndarray, valid: np.ndarray, search: int
) -> tuple[tuple[int, int], float, float | None]:
    """Integer (dy, dx) alignment of `go` onto `gi` over the valid pixels."""
    best = (0, 0)
    best_corr = -2.0
    zero_corr: float | None = None
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            shifted = np.roll(np.roll(go, -dy, axis=0), -dx, axis=1)
            c = _ncc(gi, shifted, valid)
            if dy == 0 and dx == 0:
                zero_corr = c
            if not np.isnan(c) and c > best_corr:
                best_corr = c
                best = (dy, dx)
    return best, best_corr, zero_corr


def measure(inp: Image.Image, out: Image.Image, mask: Image.Image, search: int = 16) -> Measurement:
    iw, ih = inp.size
    ow, oh = out.size
    m = Measurement(
        dims_match=(iw == ow and ih == oh),
        input_dims=(iw, ih),
        output_dims=(ow, oh),
    )
    if not m.dims_match:
        return m

    gi = _gray(inp)
    go = _gray(out)
    # Outside-mask pixels only, eroded by the search radius so shifted samples
    # never pull masked (legitimately changed) content into the comparison.
    mask_arr = np.asarray(mask.convert("L"), dtype=np.uint8) > 127
    outside = ~mask_arr
    pad = search + 2
    interior = np.zeros_like(outside)
    interior[pad:ih - pad, pad:iw - pad] = True
    valid = outside & interior
    # Also drop any pixel within `pad` of the mask.
    from scipy.ndimage import binary_dilation  # local: keeps import cost off cold paths

    grown = binary_dilation(mask_arr, iterations=pad)
    valid &= ~grown

    if valid.sum() < 1000:
        return m

    # Tile-wise alignment voting. A whole-frame search is not usable here:
    # inpaint models routinely paint new content well outside the mask (a hand,
    # a shadow, a reflection), and those pixels drag a global correlation
    # anywhere. Tiles that the model left alone all agree on the true offset;
    # tiles it repainted are outliers and get discarded by the confidence gate.
    tile = 64
    votes: dict[tuple[int, int], int] = {}
    tile_shifts: list[tuple[int, int, int, int]] = []  # cy, cx, dy, dx
    for y0 in range(0, ih - tile + 1, tile):
        for x0 in range(0, iw - tile + 1, tile):
            sub_valid = valid[y0:y0 + tile, x0:x0 + tile]
            if sub_valid.mean() < 0.9:
                continue
            ti = gi[y0:y0 + tile, x0:x0 + tile]
            if ti.std() < MIN_TILE_STD:   # flat tile: alignment is meaningless
                continue
            m.candidate_tiles += 1
            ones = np.ones_like(ti, dtype=bool)
            corrs: dict[tuple[int, int], float] = {}
            for dy in range(-search, search + 1):
                for dx in range(-search, search + 1):
                    sy0, sx0 = y0 + dy, x0 + dx
                    if sy0 < 0 or sx0 < 0 or sy0 + tile > ih or sx0 + tile > iw:
                        continue
                    c = _ncc(ti, go[sy0:sy0 + tile, sx0:sx0 + tile], ones)
                    if not np.isnan(c):
                        corrs[(dy, dx)] = c
            if not corrs:
                continue
            best_s, best_c = max(corrs.items(), key=lambda kv: kv[1])
            if best_c < MIN_TILE_CORR:    # model repainted this tile
                continue
            # Peak distinctness. A true alignment produces a sharp peak; a tile
            # matching noise correlates about equally everywhere, and its
            # "winner" is meaningless. Compare against the best correlation far
            # enough away that it cannot be the same peak.
            rival = max(
                (c for s, c in corrs.items()
                 if max(abs(s[0] - best_s[0]), abs(s[1] - best_s[1])) >= 3),
                default=-2.0,
            )
            if best_c - rival < MIN_PEAK_MARGIN:
                continue
            votes[best_s] = votes.get(best_s, 0) + 1
            tile_shifts.append((y0 + tile // 2, x0 + tile // 2, best_s[0], best_s[1]))

    m.confident_tiles = len(tile_shifts)
    if m.candidate_tiles:
        m.repaint_pct = round((1.0 - m.confident_tiles / m.candidate_tiles) * 100.0, 1)
    if tile_shifts:
        dominant = max(votes.items(), key=lambda kv: kv[1])
        m.best_shift = dominant[0]
        m.shift_agreement = round(dominant[1] / len(tile_shifts), 4)
        m.shift_votes = {f"{k[0]},{k[1]}": v for k, v in sorted(votes.items(), key=lambda kv: -kv[1])}
        # Quadrant view of the same votes: a rescale shows up as corner tiles
        # voting for shifts that point away from the centre.
        for name, pred in _QUADRANTS.items():
            quad = [(dy, dx) for cy, cx, dy, dx in tile_shifts if pred(cy, cx, ih, iw)]
            if len(quad) < MIN_QUADRANT_TILES:
                continue          # too repainted to say anything about this corner
            qv: dict[tuple[int, int], int] = {}
            for s in quad:
                qv[s] = qv.get(s, 0) + 1
            shift, count = max(qv.items(), key=lambda kv: kv[1])
            if count / len(quad) < MIN_QUADRANT_AGREEMENT:
                continue          # no consensus in this corner; the global vote rules
            m.quadrant_shifts[name] = list(shift)

    ai = np.asarray(inp.convert("RGB"), dtype=np.int16)
    ao = np.asarray(out.convert("RGB"), dtype=np.int16)
    delta = np.abs(ai - ao).max(axis=-1)

    # Spill: how much of what the model produced lands outside the mask and so
    # gets clipped away by the masked composite. High spill is not a
    # correctness failure — it is the cost of the "never trust model pixels
    # outside the mask" rule, and it predicts users needing a wider mask.
    ring_width = max(16, int(round(min(iw, ih) * 0.06)))
    ring = binary_dilation(mask_arr, iterations=ring_width) & valid
    far = valid & ~ring
    m.near_ring = _stats(delta[ring])
    m.far_field = _stats(delta[far])
    m.spill_pct = round(float((delta[valid] > 24).mean() * 100.0), 2)
    return m


def verdict_for(m: Measurement) -> tuple[str, str]:
    if not m.dims_match:
        return "whole-image", (
            f"output {m.output_dims[0]}x{m.output_dims[1]} != input "
            f"{m.input_dims[0]}x{m.input_dims[1]}"
        )
    if m.candidate_tiles < MIN_CONFIDENT_TILES:
        return "inconclusive", (
            f"the test image offers only {m.candidate_tiles} textured tiles "
            f"outside the mask (need {MIN_CONFIDENT_TILES}) — use a more "
            "detailed fixture"
        )
    if m.best_shift is None or m.confident_tiles < MIN_CONFIDENT_TILES:
        return "inconclusive", (
            f"only {m.confident_tiles} of {m.candidate_tiles} textured tiles "
            f"survived the confidence gate (need {MIN_CONFIDENT_TILES}); the "
            "model repainted too much of the frame to measure registration"
        )
    if m.shift_agreement is not None and m.shift_agreement < MIN_SHIFT_AGREEMENT:
        top = dict(list(m.shift_votes.items())[:5])
        return "whole-image", (
            f"no consensus offset: the leading vote {m.best_shift} holds only "
            f"{m.shift_agreement:.0%} of {m.confident_tiles} tiles (top votes {top}) — "
            "consistent with a rescale or a warped output"
        )
    if m.best_shift != (0, 0):
        return "whole-image", (
            f"tiles agree on shift {m.best_shift}, not (0, 0) "
            f"({m.shift_agreement:.0%} of {m.confident_tiles} tiles)"
        )
    skewed = {k: v for k, v in m.quadrant_shifts.items() if v != [0, 0]}
    if skewed:
        detail = ", ".join(f"{k}={tuple(v)}" for k, v in sorted(skewed.items()))
        return "whole-image", f"quadrants misaligned ({detail}) — output is rescaled"
    return "patch", (
        f"registered ({m.shift_agreement:.0%} of {m.confident_tiles} tiles at (0, 0)); "
        f"repainted {m.repaint_pct}% of textured tiles, spill {m.spill_pct}% of "
        f"outside-mask pixels, far-field mean {m.far_field.get('mean_abs')}"
    )


# --------------------------------------------------------------------------
# Backend client
# --------------------------------------------------------------------------

class Backend:
    def __init__(self, base_url: str, profile: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-Profile-ID": profile},
        )

    def close(self) -> None:
        self.client.close()

    def _json(self, resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            raise RuntimeError(f"{resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text[:400]}")
        return resp.json()

    def list_tools(self) -> list[dict]:
        return self._json(self.client.get("/api/tools/providers/tools"))

    def connected_provider_ids(self) -> set[str]:
        data = self._json(self.client.get("/api/tools/providers"))
        providers = data if isinstance(data, list) else data.get("providers", [])
        return {
            p.get("provider_id") for p in providers
            if p.get("status") == "connected"
        }

    def upload_image(self, path: Path) -> dict:
        with path.open("rb") as fh:
            files = {"file": (path.name, fh, "image/png")}
            return self._json(self.client.post("/api/generate/upload-reference", files=files))

    def upload_mask(self, path: Path) -> dict:
        with path.open("rb") as fh:
            files = {"file": (path.name, fh, "image/png")}
            return self._json(self.client.post("/api/generate/upload-mask", files=files))

    def submit(self, tool_id: str, task_type: str, parameters: dict) -> int:
        body = {
            "tool_id": tool_id,
            "task_type": task_type,
            "folder_path": "",
            "parameters": parameters,
            "auto_delete_duration": "24h",
            "generator_instance_id": "patch-composite-harness",
        }
        return int(self._json(self.client.post("/api/generate/submit", json=body))["job_id"])

    def job(self, job_id: int) -> dict:
        return self._json(self.client.get(f"/api/generate/jobs/{job_id}"))

    def wait_for_job(self, job_id: int, timeout_s: float, poll_s: float = 3.0) -> dict:
        deadline = time.time() + timeout_s
        last = ""
        while time.time() < deadline:
            job = self.job(job_id)
            status = job.get("status")
            if status != last:
                print(f"    job {job_id}: {status}", flush=True)
                last = status
            if status in ("completed", "failed", "cancelled"):
                return job
            time.sleep(poll_s)
        raise TimeoutError(f"job {job_id} did not finish within {timeout_s}s")

    def download_media(self, media_id: int, dest: Path) -> Path:
        resp = self.client.get(f"/api/media/{media_id}/file")
        if resp.status_code >= 400:
            raise RuntimeError(f"media {media_id} download -> {resp.status_code}")
        dest.write_bytes(resp.content)
        return dest

    def trash_media(self, media_ids: list[int]) -> None:
        if not media_ids:
            return
        try:
            self.client.post("/api/media/batch/delete", json={"media_ids": media_ids})
        except Exception as exc:  # cleanup is best-effort
            print(f"    cleanup failed: {exc}", flush=True)


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

@dataclass
class ToolResult:
    tool_id: str
    task_type: str
    status: str
    verdict: str | None = None
    reason: str | None = None
    error: str | None = None
    job_id: int | None = None
    seconds: float | None = None
    measurement: dict = field(default_factory=dict)


def discover_inpaint_tools(backend: Backend) -> list[dict]:
    tools = backend.list_tools()
    found = []
    for t in tools:
        task_types = t.get("task_types") or ([t["task_type"]] if t.get("task_type") else [])
        if INPAINT_TASK_TYPE in task_types:
            found.append(t)
    return found


def run_tool(
    backend: Backend,
    tool: dict,
    image_path: Path,
    mask_path: Path,
    out_dir: Path,
    prompt: str,
    timeout_s: float,
    keep_outputs: bool,
) -> ToolResult:
    tool_id = tool["full_tool_id"]
    result = ToolResult(tool_id=tool_id, task_type=INPAINT_TASK_TYPE, status="running")
    started = time.time()
    created_media: list[int] = []
    try:
        uploaded = backend.upload_image(image_path)
        created_media.append(int(uploaded["media_id"]))
        mask = backend.upload_mask(mask_path)

        schema_props = (tool.get("parameter_schema") or {}).get("properties", {})
        params: dict = {
            "input_images": [uploaded["path"]],
            "mask": mask["path"],
        }
        if "prompt" in schema_props:
            params["prompt"] = prompt
        if "seed" in schema_props:
            params["seed"] = 12345

        result.job_id = backend.submit(tool_id, INPAINT_TASK_TYPE, params)
        job = backend.wait_for_job(result.job_id, timeout_s)
        if job.get("status") != "completed":
            result.status = job.get("status") or "failed"
            result.error = job.get("error") or "job did not complete"
            return result

        media_id = job.get("result_media_id")
        if not media_id:
            result.status = "failed"
            result.error = "completed job has no result media"
            return result
        created_media.append(int(media_id))

        slug = tool_id.replace(":", "__").replace("/", "_")
        out_png = out_dir / f"{slug}.output.png"
        backend.download_media(int(media_id), out_png)

        inp = Image.open(image_path)
        outp = Image.open(out_png)
        maskimg = Image.open(mask_path)
        m = measure(inp, outp, maskimg)
        result.measurement = asdict(m)
        result.verdict, result.reason = verdict_for(m)
        result.status = "ok"

        if m.dims_match:
            ai = np.asarray(inp.convert("RGB"), dtype=np.int16)
            ao = np.asarray(outp.convert("RGB"), dtype=np.int16)
            dmap = np.clip(np.abs(ai - ao).max(axis=-1) * 8, 0, 255).astype(np.uint8)
            Image.fromarray(dmap, mode="L").save(out_dir / f"{slug}.diff.png")
        return result
    except Exception as exc:
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        result.seconds = round(time.time() - started, 1)
        if not keep_outputs:
            backend.trash_media(created_media)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:9191")
    ap.add_argument("--profile", required=True, help="Profile id (X-Profile-ID)")
    ap.add_argument("--tools", default="", help="Comma-separated full tool ids; default = every catalog inpaint tool")
    ap.add_argument("--image", default="", help="Test image path; default = generated test card")
    ap.add_argument("--size", default="1024x1024", help="Test card size when --image is not given")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--out-dir", default="harness-out")
    ap.add_argument("--timeout", type=float, default=600.0, help="Per-job wait, seconds")
    ap.add_argument("--keep-outputs", action="store_true", help="Leave harness media in the library")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.image:
        image_path = Path(args.image)
        img = Image.open(image_path).convert("RGB")
        image_path = out_dir / "input.png"
        img.save(image_path)
    else:
        w, h = (int(v) for v in args.size.lower().split("x"))
        img = build_test_card(w, h)
        image_path = out_dir / "input.png"
        img.save(image_path)

    mask_path = out_dir / "mask.png"
    build_mask(*img.size).save(mask_path)
    print(f"input {img.size[0]}x{img.size[1]} -> {image_path}", flush=True)

    backend = Backend(args.base_url, args.profile)
    try:
        catalog = {t["full_tool_id"]: t for t in backend.list_tools()}
        if args.tools:
            wanted = [t.strip() for t in args.tools.split(",") if t.strip()]
            missing = [t for t in wanted if t not in catalog]
            if missing:
                print(f"unknown tools: {', '.join(missing)}", file=sys.stderr)
                return 2
            tools = [catalog[t] for t in wanted]
        else:
            tools = discover_inpaint_tools(backend)

        if not tools:
            print("no inpaint tools in the catalog", file=sys.stderr)
            return 2

        connected = backend.connected_provider_ids()
        offline = [t for t in tools if t.get("provider_id") not in connected]
        tools = [t for t in tools if t.get("provider_id") in connected]
        for t in offline:
            print(
                f"  skipping {t['full_tool_id']}: provider "
                f"'{t.get('provider_id')}' is not connected",
                flush=True,
            )
        if not tools:
            print("no inpaint tools on a connected provider", file=sys.stderr)
            return 2

        print(f"testing {len(tools)} tool(s): {', '.join(t['full_tool_id'] for t in tools)}\n", flush=True)

        results: list[ToolResult] = [
            ToolResult(
                tool_id=t["full_tool_id"],
                task_type=INPAINT_TASK_TYPE,
                status="skipped",
                error=f"provider '{t.get('provider_id')}' is not connected",
            )
            for t in offline
        ]
        for tool in tools:
            print(f"  {tool['full_tool_id']}", flush=True)
            r = run_tool(
                backend, tool, image_path, mask_path, out_dir,
                args.prompt, args.timeout, args.keep_outputs,
            )
            results.append(r)
            if r.status == "ok":
                print(f"    {r.verdict.upper()} — {r.reason} ({r.seconds}s)\n", flush=True)
            else:
                print(f"    {r.status.upper()} — {r.error} ({r.seconds}s)\n", flush=True)

        report = {
            "base_url": args.base_url,
            "prompt": args.prompt,
            "input_size": list(img.size),
            "results": [asdict(r) for r in results],
        }
        report_path = out_dir / "report.json"
        report_path.write_text(json.dumps(report, indent=2))

        print("=" * 72)
        for r in results:
            label = r.verdict if r.status == "ok" else r.status
            print(f"{r.tool_id:<48} {label}")
        print(f"\nreport: {report_path}")
        return 0
    finally:
        backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
