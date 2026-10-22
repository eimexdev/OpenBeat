"""Release builds must come from one commit and pinned dependencies."""
import re
import tomllib
import unittest
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RESOLVED_SHA = "${{ needs.resolve_target.outputs.sha }}"


class ReleaseWorkflowTests(unittest.TestCase):
    def test_every_release_job_uses_the_resolved_commit(self) -> None:
        release = (WORKFLOWS / "release.yml").read_text()
        refs = re.findall(r"^\s*(?:git_)?ref: (.+)$", release, re.MULTILINE)
        # Only the first checkout sees the requested branch; it resolves the commit everything else uses.
        self.assertEqual(refs, ["${{ inputs.target }}", RESOLVED_SHA, RESOLVED_SHA])
        self.assertIn(f"RELEASE_SHA: {RESOLVED_SHA}", release)
        self.assertIn('--target "$RELEASE_SHA"', release)

    def test_build_jobs_check_out_the_requested_commit(self) -> None:
        build = (WORKFLOWS / "build-installers.yml").read_text()
        refs = re.findall(r"^\s*ref: (.+)$", build, re.MULTILINE)
        self.assertEqual(refs, ["${{ inputs.git_ref || github.sha }}"] * 2)

    def test_build_jobs_install_only_pinned_dependencies(self) -> None:
        build = (WORKFLOWS / "build-installers.yml").read_text()
        installs = set(re.findall(r"python -m pip install (.+)$", build, re.MULTILINE))
        self.assertEqual(
            installs,
            {"--upgrade pip", "--require-hashes -r requirements/build.txt", "--no-deps --no-build-isolation ."},
        )


class BuildLockTests(unittest.TestCase):
    def test_lock_pins_every_requirement_with_hashes(self) -> None:
        lock = (ROOT / "requirements" / "build.txt").read_text()
        pins: dict[str, list[str]] = {}
        for entry in re.split(r"\n(?=[^\s#])", lock):
            if entry.startswith("#"):
                continue
            match = re.match(r"([A-Za-z0-9._-]+)==([^\s;\\]+)", entry)
            self.assertIsNotNone(match, entry)
            self.assertIn("--hash=sha256:", entry)
            pins.setdefault(canonicalize_name(match.group(1)), []).append(match.group(2))

        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
        build_tools = [
            line.strip()
            for line in (ROOT / "requirements" / "build.in").read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        for requirement in map(Requirement, pyproject["project"]["dependencies"] + build_tools):
            with self.subTest(requirement=str(requirement)):
                versions = pins.get(canonicalize_name(requirement.name), [])
                self.assertTrue(versions, f"{requirement.name} is not pinned in requirements/build.txt")
                for version in versions:
                    self.assertIn(version, requirement.specifier)


if __name__ == "__main__":
    unittest.main()
