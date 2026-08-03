#!/usr/bin/env python3
"""Build the CPU-default dynamic INT8 SAM3 ONNX model set.

The source directory must contain the six upstream wkentaro/sam3-onnx-models
artifacts. Outputs retain external tensor data so quantization and runtime
loading never need to serialize multi-gigabyte embedded protobufs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import onnx
from onnxruntime.quantization import QuantType, quantize_dynamic


STEMS = ("sam3_image_encoder", "sam3_language_encoder", "sam3_decoder")


def quantize(source_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stem in STEMS:
        source = source_dir / f"{stem}.onnx"
        output = output_dir / f"{stem}.int8.onnx"
        if not source.is_file() or not source.with_suffix(".onnx.data").is_file():
            raise FileNotFoundError(f"Missing source model or external data for {source}")
        print(f"Quantizing {source.name} -> {output.name}", flush=True)
        quantize_dynamic(
            source,
            output,
            op_types_to_quantize=["MatMul", "Gemm"],
            per_channel=True,
            reduce_range=False,
            weight_type=QuantType.QInt8,
            use_external_data_format=True,
        )
        onnx.checker.check_model(output)
        print(
            f"  {output.stat().st_size + output.with_suffix('.onnx.data').stat().st_size:,} bytes",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    quantize(args.source_dir.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    main()
