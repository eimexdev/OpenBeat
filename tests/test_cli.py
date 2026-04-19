import runpy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_cli_script_runs_as_top_level_entrypoint(self) -> None:
        cli_path = ROOT / "openbeat" / "cli.py"
        previous_argv = sys.argv[:]
        try:
            sys.argv = [str(cli_path), "--help"]
            with self.assertRaises(SystemExit) as context:
                runpy.run_path(str(cli_path), run_name="__main__")
        finally:
            sys.argv = previous_argv

        self.assertEqual(context.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
