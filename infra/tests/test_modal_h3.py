"""Check Modal model-download contracts without connecting to Modal or a GPU."""

import ast
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


class TestH3Downloads(unittest.TestCase):
    def download(self, path, **kwargs):
        tree = ast.parse(path.read_text())
        constants = {"H3_FILES", "H3_REVISION", "TURBO_FILES", "TURBO_REVISION"}
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets)
        ]
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "download_models")
        function.decorator_list = []
        nodes.append(function)
        hf_download = Mock()
        models = Mock()
        with tempfile.TemporaryDirectory() as directory:
            namespace = {"MODEL_ROOT": Path(directory), "models": models}
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
            with patch.dict("sys.modules", {"huggingface_hub": types.SimpleNamespace(hf_hub_download=hf_download)}):
                result = namespace["download_models"](**kwargs)
        models.commit.assert_called_once()
        return [c.kwargs for c in hf_download.call_args_list], result

    def test_lightx_downloads_are_pinned_and_use_matching_task_adapters(self):
        paths = [ROOT / "modal_h3.py", ROOT.parents[1] / "modal_h3.py"]
        for path in paths:
            with self.subTest(path=path):
                calls, result = self.download(path)
                turbo = [c for c in calls if c["repo_id"] == "lightx2v/Minimax-h3-Turbo"]
                self.assertEqual([c["filename"] for c in turbo], [
                    "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors",
                    "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors",
                ])
                self.assertTrue(all(c["revision"] == "3ec17a324ced54151364f24f8b5fb6bf7e26414f" for c in turbo))
                self.assertTrue(all(c["local_dir"].name == "loras" for c in turbo))
                self.assertEqual(len(result["downloaded"]), len(calls))
                self.assertFalse(any("_bf16" in c["filename"] for c in calls if c["repo_id"] == "Comfy-Org/MiniMax-H3"))

    def test_disabling_reference_or_turbo_skips_the_corresponding_downloads(self):
        for path in [ROOT / "modal_h3.py", ROOT.parents[1] / "modal_h3.py"]:
            with self.subTest(path=path):
                calls, _ = self.download(path, include_reference=False)
                self.assertFalse(any("ref2v" in c["filename"] for c in calls))
                calls, _ = self.download(path, include_turbo=False)
                self.assertTrue(all(c["repo_id"] == "Comfy-Org/MiniMax-H3" for c in calls))


if __name__ == "__main__":
    unittest.main()
