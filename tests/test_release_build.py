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
        jobs = re.findall(r"^  (\w+):$", build.split("\njobs:\n", 1)[1], re.MULTILINE)
        self.assertEqual(jobs, ["test", "macos_runtime", "macos_package", "windows"])
        self.assertEqual(refs, ["${{ inputs.git_ref || github.sha }}"] * len(jobs))

    def test_build_jobs_install_only_pinned_dependencies(self) -> None:
        build = (WORKFLOWS / "build-installers.yml").read_text()
        installs = set(re.findall(r"python -m pip install (.+)$", build, re.MULTILINE))
        self.assertEqual(
            installs,
            {"--upgrade pip", "--require-hashes -r requirements/build.txt", "--no-deps --no-build-isolation ."},
        )


def job(workflow: str, name: str) -> str:
    """The text of one job in a workflow."""
    jobs = workflow.split("\njobs:\n", 1)[1]
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \w+:\n|\Z)", jobs, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(1)


class MacOSBuildWorkflowTests(unittest.TestCase):
    build = (WORKFLOWS / "build-installers.yml").read_text()

    def test_each_runtime_is_built_and_tested_on_its_own_architecture(self) -> None:
        runtime = job(self.build, "macos_runtime")
        matrix = re.findall(r"- arch: (\S+)\n\s+runner: (\S+)", runtime)
        self.assertEqual(matrix, [("arm64", "macos-15"), ("x86_64", "macos-15-intel")])
        self.assertIn("runs-on: ${{ matrix.runner }}", runtime)
        self.assertIn("--platform macos-runtime", runtime)
        self.assertIn('lipo -archs dist/openbeat', runtime)
        self.assertIn("smoke_test_runtime.py dist/openbeat", runtime)
        self.assertIn("name: openbeat-macos-runtime-${{ matrix.arch }}", runtime)

    def test_one_package_carries_both_runtimes(self) -> None:
        package = job(self.build, "macos_package")
        self.assertIn("needs: macos_runtime", package)
        self.assertIn("name: Build macos installer", package)
        self.assertIn("pattern: openbeat-macos-runtime-*", package)
        for arch in ("arm64", "x86_64"):
            self.assertIn(f"--macos-runtime {arch}=dist/runtimes/openbeat-macos-runtime-{arch}/openbeat", package)
        self.assertIn('hostArchitectures="arm64,x86_64"', package)
        self.assertIn("sudo installer", package)

    def test_release_publishes_only_the_installers(self) -> None:
        # Release downloads every artifact whose name starts with the prefix and attaches it.
        release = (WORKFLOWS / "release.yml").read_text()
        self.assertIn("artifact_prefix: release-${{ github.run_id }}", release)
        self.assertIn("pattern: release-${{ github.run_id }}-*", release)
        names = re.findall(r"uses: actions/upload-artifact@\S+\n\s+with:\n\s+name: (.+)$", self.build, re.MULTILINE)
        prefixed = [name for name in names if "inputs.artifact_prefix" in name]
        self.assertEqual(len(prefixed), 2)
        self.assertIn("'OpenBeat-macos-installer'", prefixed[0])
        self.assertIn("'OpenBeat-windows-installer'", prefixed[1])
        self.assertEqual([name for name in names if name not in prefixed], ["openbeat-macos-runtime-${{ matrix.arch }}"])
        self.assertIn("path: dist/installers/*.pkg", job(self.build, "macos_package"))
        self.assertIn("path: dist/installers/*installer.exe", job(self.build, "windows"))


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
