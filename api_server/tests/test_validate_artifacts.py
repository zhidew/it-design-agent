import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import importlib.util


SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "validate_artifacts.py"
spec = importlib.util.spec_from_file_location("validate_artifacts", SCRIPT_PATH)
validate_artifacts = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(validate_artifacts)


class ValidateArtifactsScriptTests(unittest.TestCase):
    def test_run_command_prints_unicode_failure_output_without_crashing(self):
        completed = validate_artifacts.subprocess.CompletedProcess(
            args=["demo"],
            returncode=1,
            stdout="lint failed: ✖ invalid schema",
            stderr="detail: 字段不匹配",
        )

        output = io.StringIO()
        with patch.object(validate_artifacts.subprocess, "run", return_value=completed):
            with redirect_stdout(output):
                success = validate_artifacts.run_command(["demo"])

        self.assertFalse(success)
        rendered = output.getvalue()
        self.assertIn("FAILED (Code 1)", rendered)
        self.assertIn("invalid schema", rendered)


if __name__ == "__main__":
    unittest.main()
