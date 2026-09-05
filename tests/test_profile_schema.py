from __future__ import annotations

import copy
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import yaml

from agentic_redteam.pipeline import PipelineConfigurationError
from agentic_redteam.profile.schema import Boundary, MemoryDecl, TargetProfile, ToolDecl


DATA = Path(__file__).with_name("data")


class ProfileSchemaTests(unittest.TestCase):
    def setUp(self):
        self.data = yaml.safe_load((DATA / "profile_stand.yaml").read_text())
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "profile.yaml"

    def load(self, data):
        self.path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return TargetProfile.load(self.path)

    def test_stand_fixture_preserves_target_declarations(self):
        profile = TargetProfile.load(DATA / "profile_stand.yaml")
        self.assertEqual((profile.name, profile.version, profile.adapter),
                         ("genai-invest-stand", "1.0.0", "http-chat"))
        self.assertIsInstance(profile.tools[0], ToolDecl)
        self.assertEqual(profile.tools[0].principal_from["name"], "cus")
        self.assertIsInstance(profile.memory[0], MemoryDecl)
        self.assertEqual(profile.memory[0].scope, "cross_user")
        self.assertEqual(profile.memory[1].scope_from, "record")
        self.assertIsInstance(profile.isolation[0], Boundary)
        self.assertEqual(profile.isolation[0].principal_attr, "cus")
        self.assertEqual(profile.isolation[0].principal_type, "decimal")
        self.assertEqual(profile.evidence, self.data["evidence"])
        self.assertEqual(profile.business, self.data["business"])
        self.assertEqual(profile.entrypoint, self.data["entrypoint"])
        profile.validate()

    def test_dvaa_fixture_does_not_require_stand_specific_fields(self):
        profile = TargetProfile.load(str(DATA / "profile_dvaa.yaml"))
        self.assertEqual(profile.identities["principal"]["attribute"], "agent_id")
        self.assertEqual(profile.tools[0].args, [])
        self.assertEqual(profile.tools[0].principal_from, {"kind": "none"})
        self.assertEqual(profile.isolation[0].principal_type, "string")
        self.assertEqual(profile.memory[0].scope, "cross_session")
        self.assertNotIn("commit_memory", profile.entrypoint)
        self.assertEqual(profile.business, {})

    def test_optional_sections_have_independent_defaults(self):
        minimal = {key: self.data[key] for key in ("name", "version", "adapter", "entrypoint")}
        first, second = self.load(minimal), self.load(minimal)
        self.assertEqual(first.modes, {})
        self.assertEqual(first.tools, [])
        self.assertEqual(first.memory, [])
        self.assertEqual(first.attribution, "serialized")
        first.modes["test"] = {}
        self.assertEqual(second.modes, {})

    def test_dataclass_fields_are_frozen(self):
        profile = self.load(self.data)
        for obj, attr in ((profile, "name"), (profile.tools[0], "name"),
                          (profile.memory[0], "id"), (profile.isolation[0], "id")):
            with self.subTest(type=type(obj).__name__), self.assertRaises(FrozenInstanceError):
                setattr(obj, attr, "changed")

    def test_required_fields_raise_existing_configuration_error(self):
        for key in ("name", "version", "adapter", "entrypoint"):
            invalid = copy.deepcopy(self.data)
            del invalid[key]
            with self.subTest(field=key), self.assertRaisesRegex(PipelineConfigurationError, key):
                self.load(invalid)

    def test_semver(self):
        for version in ("0.0.0", "12.30.42", "1.0.0-rc.1+build.007"):
            with self.subTest(valid=version):
                self.assertEqual(self.load({**self.data, "version": version}).version, version)
        for version in (1, "1", "1.0", "01.2.3", "1.2.3-01", "v1.2.3", "1.2.3\n"):
            with self.subTest(invalid=version), self.assertRaises(PipelineConfigurationError):
                self.load({**self.data, "version": version})

    def test_invalid_shapes_and_semantics_fail_as_configuration_errors(self):
        changes = [
            (("name",), " "), (("adapter",), 1),
            (("entrypoint",), []), (("entrypoint", "base_url"), ""),
            (("entrypoint", "base_url"), "file:///tmp/target"),
            (("entrypoint", "base_url"), "http://localhost:bad"),
            (("identities",), []), (("isolation",), {}),
            (("isolation", 0, "principal"), "cus"),
            (("surface",), []), (("surface", "tools"), {}),
            (("surface", "tools", 0), "bad"),
            (("surface", "tools", 0, "args"), "cus"),
            (("surface", "tools", 0, "sensitive"), "true"),
            (("surface", "tools", 0, "principal_from", "kind"), "guessed"),
            (("surface", "tools", 0, "principal_from", "name"), ""),
            (("surface", "memory", 0, "scope"), "global"),
            (("surface", "memory", 0, "scope_from"), "record"),
            (("surface", "memory", 0, "read"), "db-query"),
            (("surface", "memory", 0, "record", "content"), None),
            (("surface", "memory", 1, "scope_from"), "guessed"),
            (("surface", "memory", 1, "record", "scope", "map", "global"), "global"),
            (("modes",), []), (("modes", "protected", "scope"), "global"),
            (("evidence",), {}), (("evidence", 0, "config"), []),
            (("attribution",), "guessed"), (("business",), []),
        ]
        for path, value in changes:
            invalid = copy.deepcopy(self.data)
            parent = invalid
            for part in path[:-1]:
                parent = parent[part]
            parent[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(PipelineConfigurationError):
                self.load(invalid)

    def test_duplicate_declaration_ids_are_rejected(self):
        for section in ("tools", "memory"):
            invalid = copy.deepcopy(self.data)
            invalid["surface"][section].append(invalid["surface"][section][0])
            with self.subTest(section=section), self.assertRaises(PipelineConfigurationError):
                self.load(invalid)

    def test_validate_also_checks_directly_constructed_profiles(self):
        profile = self.load(self.data)
        with self.assertRaises(PipelineConfigurationError):
            replace(profile, version="bad").validate()
        with self.assertRaises(PipelineConfigurationError):
            replace(profile, tools=[replace(profile.tools[0], sensitive="true")]).validate()

    def test_plaintext_credentials_are_rejected_but_env_names_are_preserved(self):
        for credential in ("Bearer actual-secret", "actual-secret"):
            invalid = copy.deepcopy(self.data)
            invalid["identities"]["credential"]["headers"]["Authorization"] = credential
            with self.subTest(credential=credential), self.assertRaises(PipelineConfigurationError) as caught:
                self.load(invalid)
            self.assertNotIn("actual-secret", str(caught.exception))
        self.assertEqual(self.load(self.data).memory[0].read["config"]["uri_env"], "TARGET_MONGO_URI")

    def test_bad_yaml_root_and_missing_file_are_configuration_errors(self):
        for content in ("", "[]", "name: [", "!!python/object:builtins.object {}"):
            self.path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(PipelineConfigurationError):
                TargetProfile.load(self.path)
        with self.assertRaises(PipelineConfigurationError):
            TargetProfile.load(self.path.with_name("missing.yaml"))


if __name__ == "__main__":
    unittest.main()
