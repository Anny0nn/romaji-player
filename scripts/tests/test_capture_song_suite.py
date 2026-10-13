"""Offline immutable-helper and private-output checks; never access Keychain."""

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "capture", Path(__file__).resolve().parents[1] / "capture-song-suite.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureTests(unittest.TestCase):
    def test_changed_preserved_binary_cannot_silently_request_access_again(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch)
            executable = folder / "record_alignment_acceptance"
            executable.write_bytes(b"synthetic helper")
            executable.chmod(0o700)
            (folder / "sha256").write_text(
                hashlib.sha256(executable.read_bytes()).hexdigest()
            )
            self.assertEqual(module.authorized_helper(folder), executable)
            executable.write_bytes(b"rebuilt helper")
            with self.assertRaisesRegex(ValueError, "helper changed"):
                module.authorized_helper(folder)

    def test_ids_are_explicit_arguments_and_capture_never_invokes_cargo(self):
        with tempfile.TemporaryDirectory(prefix="capture with spaces ") as scratch:
            output = Path(scratch) / "private"
            ids = ["2dkIbR4mudsHg45av3YwxQ"]
            with patch.object(module.subprocess, "run") as run:
                module.capture(output, ids, Path("immutable helper"))
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            run.assert_called_once_with(
                ["immutable helper", str(output.resolve()), "--stereo", *ids],
                check=True,
            )

    def test_untrusted_ids_and_repository_outputs_never_launch_helper(self):
        for ids in ([], ["../escape"], ["a" * 22, "a" * 22], ["a" * 21]):
            with self.assertRaises(ValueError):
                module.track_ids(ids)
        with patch.object(module.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "outside the repository"):
                module.capture(module.ROOT / "data", ["a" * 22], Path("helper"))
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
