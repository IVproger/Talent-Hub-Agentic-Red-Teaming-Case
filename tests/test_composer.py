import unittest
from agentic_redteam.generation.template import Template
from agentic_redteam.generation.composer import (
    compose, Unsupported, profile_features, profile_capabilities,
)
from agentic_redteam.campaign.scenarios import ScenarioSpec
from agentic_redteam.profile.schema import TargetProfile

STAND = TargetProfile.load("tests/data/profile_stand.yaml")
DVAA = TargetProfile.load("tests/data/profile_dvaa.yaml")


def template(**over):
    base = dict(
        id="t", standard={"asi": "ASI06", "atlas": ["AML.T0051"]}, title="T",
        boundary="user", delivery=["user_message"],
        requires_features=[], requires_evidence=["tool_calls"], enhanced_by=["memory_snapshot"],
        steps=[{"role": "attacker", "act": "inject", "payload": True},
               {"role": "victim", "act": "activate", "message": "мой портфель?"}],
        success=[{"assert": "tool_principal_mismatch", "at": "activate"}],
        remediation="R",
    )
    base.update(over)
    return Template(**base)


class ComposeTests(unittest.TestCase):
    def test_compose_produces_a_scenario_spec(self):
        spec = compose(template(), STAND, profile_capabilities(STAND))
        self.assertIsInstance(spec, ScenarioSpec)
        self.assertEqual(spec.boundary, "user")
        self.assertIn("ASI06", spec.standard_refs)
        self.assertIn("AML.T0051", spec.standard_refs)
        self.assertEqual([s.name for s in spec.steps], ["inject", "activate"])
        self.assertTrue(spec.steps[0].payload)
        self.assertEqual(spec.steps[1].message, "мой портфель?")
        self.assertEqual([a["type"] for a in spec.goal], ["tool_principal_mismatch"])

    def test_boundary_absent_on_target_is_not_applicable(self):
        # DVAA объявляет только границу session, не user.
        result = compose(template(boundary="user"), DVAA, profile_capabilities(DVAA))
        self.assertIsInstance(result, Unsupported)
        self.assertEqual(result.kind, "not_applicable")
        self.assertIn("user", result.reason)

    def test_missing_evidence_is_unsupported(self):
        result = compose(template(requires_evidence=["external_callback"]), STAND,
                         profile_capabilities(STAND))
        self.assertIsInstance(result, Unsupported)
        self.assertEqual(result.kind, "unsupported")
        self.assertIn("external_callback", result.reason)

    def test_missing_feature_is_unsupported(self):
        # DVAA не объявляет commit_memory (нет entrypoint.commit_memory).
        result = compose(template(boundary="session", requires_features=["memory_commit"],
                                  requires_evidence=[],
                                  steps=[{"role": "attacker", "act": "inject", "payload": True},
                                         {"role": "attacker", "act": "commit_memory"},
                                         {"role": "victim", "act": "activate", "message": "?"}],
                                  success=[{"assert": "cross_session_effect",
                                            "inject": "inject", "activate": "activate"}]),
                         DVAA, profile_capabilities(DVAA))
        self.assertIsInstance(result, Unsupported)
        self.assertIn("memory_commit", result.reason)

    def test_enhanced_assertion_included_only_with_snapshot(self):
        tmpl = template(success=[{"assert": "tool_principal_mismatch", "at": "activate"},
                                 {"assert": "memory_write", "scope": "cross_user", "when": "enhanced"}])
        with_snapshot = compose(tmpl, STAND, {"tool_calls", "memory_snapshot"})
        self.assertEqual([a["type"] for a in with_snapshot.goal],
                         ["tool_principal_mismatch", "memory_write"])
        self.assertNotIn("when", with_snapshot.goal[1])
        without = compose(tmpl, STAND, {"tool_calls"})
        self.assertEqual([a["type"] for a in without.goal], ["tool_principal_mismatch"])

    def test_commit_memory_step_binds_to_finalize(self):
        spec = compose(template(boundary="session", requires_features=["memory_commit"],
                                steps=[{"role": "attacker", "act": "inject", "payload": True},
                                       {"role": "attacker", "act": "commit_memory"},
                                       {"role": "victim", "act": "activate", "message": "?"}],
                                success=[{"assert": "cross_session_effect",
                                          "inject": "inject", "activate": "activate"}]),
                       STAND, profile_capabilities(STAND))
        self.assertIsInstance(spec, ScenarioSpec)
        self.assertTrue(spec.steps[1].commit_memory)


class ProfileIntrospectionTests(unittest.TestCase):
    def test_capabilities_from_evidence_and_memory(self):
        self.assertEqual(profile_capabilities(STAND), {"tool_calls", "memory_snapshot"})

    def test_features_from_entrypoint(self):
        self.assertIn("memory_commit", profile_features(STAND))
        self.assertNotIn("memory_commit", profile_features(DVAA))
