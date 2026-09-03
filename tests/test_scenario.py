from __future__ import annotations

import unittest

from agentic_redteam.scenario import bundled_scenarios, load_bundled_scenario


class BundledScenarioTests(unittest.TestCase):
    def test_catalog_loads_every_supported_scenario(self):
        self.assertEqual(
            set(bundled_scenarios()),
            {
                "bac-tool-argument",
                "mem-policy-conformant",
                "poison-to-tool-chain",
                "system-prompt-leak",
            },
        )

    def test_runtime_identities_render_into_steps_and_assertions(self):
        scenario = load_bundled_scenario("bac-tool-argument").with_runtime_values(
            "7001", "7999", "protected"
        )

        self.assertEqual(scenario.roles["attacker"]["cus"], "7001")
        self.assertEqual(scenario.params["target_cus"], "7999")
        self.assertEqual(scenario.steps[0]["auth_mode"], "protected")
        self.assertIn("7999", scenario.render(scenario.steps[0]["message"]))
        self.assertEqual(scenario.render(scenario.goal[1]["value"]), "7999")

    def test_system_prompt_leak_uses_runtime_actor_identity(self):
        scenario = load_bundled_scenario("system-prompt-leak").with_runtime_values(
            "8111", "8222", "vulnerable"
        )
        self.assertEqual(scenario.roles["attacker"]["cus"], "8111")
        self.assertEqual(scenario.render(scenario.goal[0]["value"]), "cus=8111")


if __name__ == "__main__":
    unittest.main()
