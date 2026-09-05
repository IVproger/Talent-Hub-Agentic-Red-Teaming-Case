import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from agentic_redteam.errors import PipelineConfigurationError
from agentic_redteam.profile.registry import ProfileRegistry
from agentic_redteam.profile.schema import TargetProfile


class ProfileRegistryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve() / "profiles"
        self.registry = ProfileRegistry(self.root)
        self.profile = TargetProfile.load(Path(__file__).with_name("data") / "profile_stand.yaml")

    def test_round_trip_restores_surface_and_principal_declarations(self):
        path = self.registry.save(self.profile)
        self.assertEqual(path, self.root / self.profile.name / "1.0.0.yaml")
        self.assertEqual(self.registry.load(self.profile.name, "1.0.0"), self.profile)
        self.assertEqual(self.registry.list(), [(self.profile.name, "1.0.0")])
        self.assertIn("surface:", path.read_text())

    def test_unknown_empty_and_immutable_versions(self):
        self.assertEqual(self.registry.list(), [])
        with self.assertRaises(PipelineConfigurationError):
            self.registry.load("unknown", "1.0.0")
        path = self.registry.save(self.profile)
        original = path.read_bytes()
        with self.assertRaises(PipelineConfigurationError):
            self.registry.save(replace(self.profile, business={"changed": True}))
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_identifiers_cannot_escape_root(self):
        for name, version in (("../outside", "1.0.0"), ("/tmp/escape", "1.0.0"),
                              ("ok", "../../outside"), (".", "1.0.0")):
            with self.subTest(name=name, version=version), self.assertRaises(PipelineConfigurationError):
                self.registry.load(name, version)

    def test_symlink_and_mismatched_identity_are_rejected(self):
        self.root.mkdir()
        (self.root / self.profile.name).symlink_to(Path(self.directory.name), target_is_directory=True)
        with self.assertRaises(PipelineConfigurationError):
            self.registry.save(self.profile)
        (self.root / self.profile.name).unlink()
        path = self.registry.save(self.profile)
        path.write_text(path.read_text().replace("name: genai-invest-stand", "name: renamed"))
        with self.assertRaises(PipelineConfigurationError):
            self.registry.load(self.profile.name, "1.0.0")

    def test_bootstrap_profile_is_loadable(self):
        root = Path(__file__).resolve().parents[1] / "profiles"
        profile = ProfileRegistry(root).load("genai-invest-stand", "1.0.0")
        self.assertEqual(profile.adapter, "http-chat")


if __name__ == "__main__":
    unittest.main()
