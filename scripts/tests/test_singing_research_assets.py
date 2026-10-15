"""No remote code, changed weights, missing runtime layers, or archive links."""

import importlib.util
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def module(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), Path(__file__).resolve().parents[1] / f"{name}.py"
    )
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


fetcher = module("fetch-singing-research")
runner = module("transcribe-singing-crops")


class SingingResearchAssets(unittest.TestCase):
    def test_runtime_rejects_links_traversal_and_changed_existing_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "source.tar"
            output = root / "runtime"
            commit = "abc123"
            for path, link in (
                ("mlx-audio-abc123/../../secret", False),
                ("other/package.py", False),
                ("mlx-audio-abc123/link", True),
            ):
                with tarfile.open(archive, "w") as tar:
                    member = tarfile.TarInfo(path)
                    member.size = 1
                    if link:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "/tmp/private"
                    tar.addfile(member, io.BytesIO(b"x"))
                with self.assertRaises(ValueError):
                    fetcher.extract_runtime(archive, output, commit)
            with tarfile.open(archive, "w") as tar:
                member = tarfile.TarInfo("mlx-audio-abc123/package.py")
                member.size = 1
                tar.addfile(member, io.BytesIO(b"x"))
            fetcher.extract_runtime(archive, output, commit)
            fetcher.extract_runtime(archive, output, commit)
            (output / "package.py").write_text("changed")
            with self.assertRaises(ValueError):
                fetcher.extract_runtime(archive, output, commit)

    def test_fixed_prompts_have_audio_placeholder_and_no_lyrics(self):
        self.assertEqual(runner.PROMPT, "Transcribe the lyrics of this song.")
        self.assertIn("<|audio_bos|><|AUDIO|><|audio_eos|>", runner.DIRECT_PROMPT)
        self.assertTrue(runner.DIRECT_PROMPT.endswith("<think>\n\n</think>\n\n"))
        self.assertIn(
            "Transcribe the lyrics with timestamps of this song.", runner.DIRECT_PROMPT
        )

    def test_changed_cached_download_is_rejected_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model"
            path.write_bytes(b"wrong")
            with self.assertRaises(ValueError):
                fetcher.fetch(
                    path,
                    "https://example.invalid/no-network",
                    runner.KNOWN_ASSETS["model.safetensors"][1],
                )
