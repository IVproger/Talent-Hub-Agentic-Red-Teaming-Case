import copy
import unittest
from dataclasses import replace
from pathlib import Path

from agentic_redteam.profile.diff import diff
from agentic_redteam.profile.schema import TargetProfile, ToolDecl


class ProfileDiffTests(unittest.TestCase):
    def setUp(self):
        self.profile = TargetProfile.load(Path(__file__).with_name("data") / "profile_stand.yaml")

    def test_equal_and_version_only_changes_have_no_surface_diff(self):
        self.assertEqual(diff(self.profile, copy.deepcopy(self.profile)), {})
        self.assertEqual(diff(self.profile, replace(self.profile, version="2.0.0")), {})

    def test_added_removed_changed_declarations_and_endpoint(self):
        updated = replace(self.profile,
            tools=[replace(self.profile.tools[0], sensitive=False),
                   ToolDecl("new_tool", [], False, {"kind": "none"})],
            memory=self.profile.memory[1:],
            identities={**self.profile.identities, "roles": {"attacker": {"cus": "3"}}},
            entrypoint={**self.profile.entrypoint, "base_url": "http://new-host"})
        result = diff(self.profile, updated)
        self.assertEqual(set(result), {"tools", "roles", "memory", "entrypoint"})
        self.assertIn("new_tool", result["tools"]["added"])
        self.assertTrue(result["tools"]["changed"]["get_portfolio"]["before"]["sensitive"])
        self.assertIn("policy", result["memory"]["removed"])
        self.assertIn("victim", result["roles"]["removed"])
        self.assertEqual(result["entrypoint"]["changed"]["base_url"]["after"], "http://new-host")
        result["roles"]["removed"]["victim"]["cus"] = "mutated"
        self.assertEqual(self.profile.identities["roles"]["victim"]["cus"], "1002")

    def test_declaration_order_is_not_a_change(self):
        self.assertEqual(diff(self.profile, replace(self.profile, memory=list(reversed(self.profile.memory)))), {})
