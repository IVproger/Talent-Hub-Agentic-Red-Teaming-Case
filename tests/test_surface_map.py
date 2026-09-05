import unittest

from agentic_redteam.doctor import CheckResult
from agentic_redteam.profile.schema import TargetProfile
from agentic_redteam.surface.map import build_surface, declared_capabilities


PROFILE = TargetProfile.load("tests/data/profile_stand.yaml")


class SurfaceMapTests(unittest.TestCase):
    def test_declared_components_remain_visible_when_not_calibrated(self):
        surface = build_surface(PROFILE)
        self.assertEqual(surface["profile"], "genai-invest-stand@1.0.0")
        self.assertEqual(surface["adapter"], "http-chat")
        self.assertEqual(surface["tools"][0]["status"], "заявлен, но не подтверждён")
        self.assertEqual(surface["memory"][0]["status"], "заявлен, но не подтверждён")

    def test_calibration_is_attributed_to_the_matching_component(self):
        surface = build_surface(PROFILE, [
            CheckResult("target", True, "API доступен"),
            CheckResult("tool_calls", True, "Лог доступен"),
            CheckResult("memory:policy", False, "Коллекция пуста", blocking=False),
        ])
        self.assertEqual(surface["entrypoints"][0]["status"], "подключён")
        evidence = {item["id"]: item for item in surface["evidence"]}
        self.assertEqual(evidence["tool_calls"]["status"], "подключён")
        memory = {item["id"]: item for item in surface["memory"]}
        self.assertEqual(memory["policy"]["status"], "недоступен")
        self.assertEqual(memory["policy"]["reason"], "Коллекция пуста")

    def test_dict_results_from_the_ui_use_the_same_mapping(self):
        surface = build_surface(
            PROFILE, [{"name": "target", "ok": True, "message": "ok"}]
        )
        self.assertEqual(surface["entrypoints"][0]["status"], "подключён")

    def test_capabilities_include_evidence_and_declared_memory(self):
        self.assertEqual(
            declared_capabilities(PROFILE),
            {"tool_calls", "memory_snapshot"},
        )


if __name__ == "__main__":
    unittest.main()
