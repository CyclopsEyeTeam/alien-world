"""Native build failures must not be reported as successful builds."""
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent


class NativeBuildTests(unittest.TestCase):
    def test_compiler_failure_fails_make(self):
        with tempfile.TemporaryDirectory(prefix='aw-build-') as tmp:
            result = subprocess.run(
                [
                    'make', '--no-print-directory', '-B', 'build',
                    'CC=false', 'PY_INCLUDES=-Iunused',
                    f'FAST_CELLS_SO={tmp}/fast-cells.so',
                ],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
            )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('Built ', result.stdout)
