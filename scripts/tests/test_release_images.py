"""Focused safety checks for the release image command."""

import hashlib
import importlib.util
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "release-images.py"
SPEC = importlib.util.spec_from_file_location("release_images", SCRIPT)
release_images = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_images)


class ReleaseValidationTests(unittest.TestCase):
    def parsed(self, *extra):
        return release_images.build_parser().parse_args(["--version", "v1.2.3", *extra])

    def test_rejects_non_semver_version_before_git_access(self):
        args = self.parsed()
        args.version = "latest"
        with patch.object(release_images, "run") as run, self.assertRaisesRegex(ValueError, "semantic release tag"):
            release_images.validate(args)
        run.assert_not_called()

    def test_publish_requires_expected_revision(self):
        args = self.parsed("--push", "--repository", "acme/cap", "--lifecycle")
        with patch.object(release_images, "git_revision", return_value="a" * 40), patch.object(release_images, "run") as run, self.assertRaisesRegex(ValueError, "requires --expected-revision"):
            release_images.validate(args)
        run.assert_not_called()

    def test_publish_requires_lifecycle_rehearsal(self):
        args = self.parsed("--push", "--repository", "acme/cap", "--expected-revision", "a" * 40)
        with patch.object(release_images, "git_revision", return_value="a" * 40), patch.object(
            release_images, "run", return_value=SimpleNamespace(stdout="v1.2.3\n")
        ), self.assertRaisesRegex(ValueError, "requires the install/upgrade/restore"):
            release_images.validate(args)

    def test_publish_requires_exact_semver_git_tag(self):
        args = self.parsed("--push", "--lifecycle", "--repository", "acme/cap", "--expected-revision", "a" * 40)
        with patch.object(release_images, "git_revision", return_value="a" * 40), patch.object(
            release_images,
            "run",
            side_effect=[SimpleNamespace(stdout=""), SimpleNamespace(stdout="b" * 40 + "\n")],
        ), self.assertRaisesRegex(ValueError, "version tag must resolve directly"):
            release_images.validate(args)

    def test_publish_rejects_dirty_tracked_or_untracked_tree(self):
        args = self.parsed("--push", "--lifecycle", "--repository", "acme/cap", "--expected-revision", "a" * 40)
        with patch.object(release_images, "git_revision", return_value="a" * 40), patch.object(
            release_images,
            "run",
            side_effect=[SimpleNamespace(stdout="?? untracked.txt\n"), SimpleNamespace(stdout="a" * 40 + "\n")],
        ), self.assertRaisesRegex(ValueError, "clean tracked and untracked"):
            release_images.validate(args)

    def test_rejects_revision_mismatch(self):
        args = self.parsed("--expected-revision", "b" * 40)
        with patch.object(release_images, "git_revision", return_value="a" * 40), self.assertRaisesRegex(ValueError, "does not match"):
            release_images.validate(args)

    def test_structured_ocr_smoke_runs_both_engines_and_records_image_provenance(self):
        args = self.parsed("--context", "desktop-linux")
        commands = []

        def fake_run(command, *, cwd=release_images.ROOT, capture_output=False):
            commands.append(command)
            if "id" in command:
                output = "10001\n"
            elif "cat" in command:
                output = '{"source_version":"5.5.3","sha256":"' + "f" * 64 + '"}'
            else:
                output = ""
            return SimpleNamespace(stdout=output, stderr="")

        with tempfile.TemporaryDirectory() as temporary:
            args.output = Path(temporary)
            with patch.object(release_images, "run", side_effect=fake_run):
                result = release_images.run_smoke_checks(args, Path("/export"), "backend-structured-ocr", "cap:check")
            self.assertEqual(result.name, "backend-structured-ocr-ocr-build.json")
            saved = json.loads(result.read_text())
            self.assertEqual(saved["source_version"], "5.5.3")
            self.assertTrue(any("CAP_OCR_SMOKE_ENGINE=opendataloader" in command for command in commands))
            self.assertTrue(any("--context" in command and "desktop-linux" in command for command in commands))
            self.assertTrue(any("sample_requirements.pdf" in " ".join(command) for command in commands))

    def publish_fixture(self, temporary, *, failing_scan=None, bad_report=None, manifest_ids=False):
        revision = "a" * 40
        args = self.parsed(
            "--push", "--lifecycle", "--repository", "acme/cap", "--expected-revision", revision,
            "--context", "explicit-release-context",
        )
        args.output = Path(temporary)
        events = []
        exported_ids = {}
        configs = {name: json.dumps({"image": name}).encode() for name in release_images.IMAGES}
        config_ids = {name: "sha256:" + hashlib.sha256(config).hexdigest() for name, config in configs.items()}
        image_ids = {
            name: "sha256:" + str(index + 1) * 64 if manifest_ids else config_ids[name]
            for index, name in enumerate(configs)
        }

        def fake_run(command, *, cwd=release_images.ROOT, capture_output=False, env=None):
            if command[0] == "git" and command[1] == "rev-parse":
                return SimpleNamespace(stdout=revision + "\n", stderr="")
            if command[0] == "git" and command[1] == "describe":
                return SimpleNamespace(stdout="v1.2.3\n", stderr="")
            if command[0] == "git" and command[1] == "status":
                return SimpleNamespace(stdout="", stderr="")
            if command[0] == release_images.sys.executable and command[1].endswith("export-public.py"):
                self.assertIn("--check-tracked", command)
                self.assertNotIn("--draft", command)
                export_path = Path(command[command.index("--output") + 1])
                export_path.mkdir(parents=True, exist_ok=True)
                (export_path / "SNAPSHOT.json").write_text('{"draft":false}\n')
                events.append("export")
            if command[0] == "docker":
                self.assertEqual(command[1:3], ["--context", args.context])
                operation = command[3]
                if operation == "buildx":
                    events.append("build")
                    metadata = Path(command[command.index("--metadata-file") + 1])
                    metadata.write_text(json.dumps({"containerimage.digest": "sha256:" + "b" * 64}))
                elif operation == "image":
                    if command[4] == "inspect":
                        name = command[-1].split("/")[1].split(":")[0]
                        return SimpleNamespace(stdout=image_ids[name] + "\n", stderr="")
                    self.assertEqual(command[4], "save")
                    self.assertIn(command[-1], image_ids.values())
                    archive_path = command[command.index("--output") + 1]
                    name = next(name for name, value in image_ids.items() if value == command[-1])
                    exported_ids[archive_path] = config_ids[name]
                    with tarfile.open(archive_path, "w") as archive:
                        for filename, content in {
                            "manifest.json": b'[{"Config":"config.json"}]',
                            "config.json": configs[name],
                        }.items():
                            info = tarfile.TarInfo(filename)
                            info.size = len(content)
                            archive.addfile(info, io.BytesIO(content))
                    events.append("save")
                elif operation == "tag":
                    events.append("tag")
                elif operation == "push":
                    events.append("push")
                    return SimpleNamespace(stdout="digest: sha256:" + "d" * 64 + " size: 123\n", stderr="")
            elif command[0] == "/tools/grype":
                events.append("scan")
                self.assertEqual(command[command.index("--fail-on") + 1], "high")
                self.assertEqual(command[command.index("--output") + 1], "json")
                self.assertFalse(any(key.startswith(("GRYPE_", "SYFT_")) for key in env))
                self.assertNotIn("--only-fixed", command)
                self.assertNotIn("--ignore-unfixed", command)
                config = Path(command[command.index("--config") + 1]).read_text()
                self.assertIn("ignore: []", config)
                self.assertIn("only-fixed: false", config)
                archive = command[1].removeprefix("docker-archive:")
                self.assertTrue(command[1].startswith("docker-archive:"))
                report = Path(command[command.index("--file") + 1])
                report.write_text(json.dumps({
                    "matches": [],
                    "source": {"type": "image", "target": {
                        "imageID": "sha256:" + "f" * 64 if bad_report == "wrong-image" else exported_ids[archive],
                    }},
                }))
                if bad_report == "missing":
                    report.unlink()
                elif bad_report == "malformed":
                    report.write_text("not-json")
                elif bad_report == "incomplete":
                    report.write_text("{}")
                if events.count("scan") == failing_scan:
                    raise subprocess.CalledProcessError(2, command)
            elif len(command) > 1 and command[1].endswith("check-release-lifecycle.py"):
                events.append("lifecycle")
            return SimpleNamespace(stdout="", stderr="")

        return args, events, image_ids, fake_run

    def test_publish_builds_tests_and_scans_all_same_local_images_before_push(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, events, image_ids, fake_run = self.publish_fixture(temporary)
            with patch.object(release_images, "run", side_effect=fake_run), patch.object(
                release_images, "run_smoke_checks", return_value=None
            ) as smoke, patch.object(release_images.shutil, "which", return_value="/tools/grype"), patch.dict(
                release_images.os.environ, {"GRYPE_ONLY_FIXED": "true", "SYFT_DOCKER_HOST": "tcp://wrong-daemon:2375"}
            ):
                release_images.build(args)
            self.assertEqual(smoke.call_count, 5)
            self.assertEqual(events.count("build"), 5)
            self.assertLess(events.index("lifecycle"), events.index("tag"))
            self.assertEqual(events.count("save"), 5)
            self.assertEqual(events.count("scan"), 5)
            self.assertLess(max(index for index, event in enumerate(events) if event == "scan"), events.index("tag"))
            self.assertEqual(events.count("tag"), 10)
            self.assertEqual(events.count("push"), 10)
            metadata = json.loads((args.output / "release-metadata.json").read_text())
            snapshot_bytes = (args.output / "source-snapshot.json").read_bytes()
            self.assertEqual(metadata["source_snapshot_sha256"], hashlib.sha256(snapshot_bytes).hexdigest())
            self.assertEqual(metadata["source_revision"], "a" * 40)
            self.assertTrue(metadata["working_tree_clean"])
            for name, image in metadata["images"].items():
                self.assertEqual(image["local_image_id"], image_ids[name])
                self.assertEqual(image["registry_manifest_digest"], "sha256:" + "d" * 64)
                self.assertEqual(image["vulnerability_report"], f"{name}.grype.json")
                self.assertEqual(image["scanned_config_digest"], image_ids[name])

    def test_containerd_manifest_ids_verify_against_the_exported_config_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, events, image_ids, fake_run = self.publish_fixture(temporary, manifest_ids=True)
            with patch.object(release_images, "run", side_effect=fake_run), patch.object(
                release_images, "run_smoke_checks", return_value=None
            ), patch.object(release_images.shutil, "which", return_value="/tools/grype"):
                release_images.build(args)
            metadata = json.loads((args.output / "release-metadata.json").read_text())
            for name, image in metadata["images"].items():
                self.assertEqual(image["local_image_id"], image_ids[name])
                self.assertNotEqual(image["scanned_config_digest"], image_ids[name])
            self.assertEqual(events.count("scan"), 5)
            self.assertEqual(events.count("push"), 10)

    def test_first_or_last_scan_failure_prevents_every_registry_tag_and_push(self):
        for failing_scan in (1, 5):
            with self.subTest(failing_scan=failing_scan), tempfile.TemporaryDirectory() as temporary:
                args, events, _, fake_run = self.publish_fixture(temporary, failing_scan=failing_scan)
                with patch.object(release_images, "run", side_effect=fake_run), patch.object(
                    release_images, "run_smoke_checks", return_value=None
                ), patch.object(release_images.shutil, "which", return_value="/tools/grype"), self.assertRaises(
                    subprocess.CalledProcessError
                ):
                    release_images.build(args)
                self.assertEqual(events.count("scan"), failing_scan)
                self.assertNotIn("tag", events)
                self.assertNotIn("push", events)
                self.assertEqual(len(list(args.output.glob("*.grype.json"))), failing_scan)

    def test_report_for_wrong_image_prevents_every_registry_tag_and_push(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, events, _, fake_run = self.publish_fixture(temporary, bad_report="wrong-image")
            with patch.object(release_images, "run", side_effect=fake_run), patch.object(
                release_images, "run_smoke_checks", return_value=None
            ), patch.object(release_images.shutil, "which", return_value="/tools/grype"), self.assertRaisesRegex(
                ValueError, "does not match the exported image configuration"
            ):
                release_images.build(args)
            self.assertNotIn("tag", events)
            self.assertNotIn("push", events)

    def test_missing_malformed_or_incomplete_report_prevents_publication(self):
        for bad_report in ("missing", "malformed", "incomplete"):
            with self.subTest(bad_report=bad_report), tempfile.TemporaryDirectory() as temporary:
                args, events, _, fake_run = self.publish_fixture(temporary, bad_report=bad_report)
                with patch.object(release_images, "run", side_effect=fake_run), patch.object(
                    release_images, "run_smoke_checks", return_value=None
                ), patch.object(release_images.shutil, "which", return_value="/tools/grype"), self.assertRaises(
                    ValueError
                ):
                    release_images.build(args)
                self.assertNotIn("tag", events)
                self.assertNotIn("push", events)

    def test_missing_scanner_fails_before_export_or_build(self):
        args = self.parsed("--push")
        with patch.object(release_images, "validate", return_value=("a" * 40, True)), patch.object(
            release_images.shutil, "which", return_value=None
        ), patch.object(release_images, "run") as run, self.assertRaisesRegex(ValueError, "requires Grype"):
            release_images.build(args)
        run.assert_not_called()

    def test_dirty_draft_records_snapshot_without_claiming_clean_revision(self):
        revision = "e" * 40
        args = self.parsed()
        build_commands = []

        def fake_run(command, *, cwd=release_images.ROOT, capture_output=False):
            if command[0] == release_images.sys.executable and command[1].endswith("export-public.py"):
                self.assertIn("--draft", command)
                export_path = Path(command[command.index("--output") + 1])
                export_path.mkdir(parents=True, exist_ok=True)
                (export_path / "SNAPSHOT.json").write_text('{"draft":true}\n')
            elif command[0] == "docker":
                self.assertEqual(command[1:3], ["--context", args.context])
                if command[3] == "buildx":
                    build_commands.append(command)
                    Path(command[command.index("--metadata-file") + 1]).write_text("{}")
                elif command[3] == "image":
                    return SimpleNamespace(stdout="sha256:" + "f" * 64 + "\n", stderr="")
            return SimpleNamespace(stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temporary:
            args.output = Path(temporary)
            with patch.object(release_images, "validate", return_value=(revision, False)), patch.object(
                release_images, "run", side_effect=fake_run
            ), patch.object(release_images, "run_smoke_checks", return_value=None), patch.object(
                release_images.shutil, "which", side_effect=AssertionError("Draft builds must not require a scanner")
            ):
                release_images.build(args)
            metadata = json.loads((args.output / "release-metadata.json").read_text())
            self.assertIsNone(metadata["source_revision"])
            self.assertEqual(metadata["base_revision"], revision)
            self.assertFalse(metadata["working_tree_clean"])
            self.assertTrue(all(tag.endswith("-working-tree") for item in metadata["images"].values() for tag in item["tags"]))
            self.assertTrue(all("VCS_REF=unknown" in command for command in build_commands))
            snapshot = (args.output / "source-snapshot.json").read_bytes()
            self.assertEqual(metadata["source_snapshot_sha256"], hashlib.sha256(snapshot).hexdigest())


if __name__ == "__main__":
    unittest.main()
