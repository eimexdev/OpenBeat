import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUA = shutil.which("lua") or shutil.which("lua5.1") or shutil.which("lua5.4")


@unittest.skipUnless(LUA, "Lua is required to test the Resolve scripts")
class ResolveTests(unittest.TestCase):
    def test_lua_behavior(self) -> None:
        for script in sorted((ROOT / "tests" / "lua").glob("test_*.lua")):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [LUA, str(script)], cwd=ROOT, text=True, capture_output=True, timeout=30
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
