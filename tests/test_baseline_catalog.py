import tempfile, unittest
from pathlib import Path
from agentic_redteam.generation.freeze import freeze_baseline
from agentic_redteam.campaign.scenarios import ScenarioSpec
from agentic_redteam.profile.schema import TargetProfile

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
STAND = TargetProfile.load("tests/data/profile_stand.yaml")


class FreezeBaselineTests(unittest.TestCase):
    def test_freeze_writes_loadable_scenarios(self):
        out = Path(tempfile.mkdtemp())
        paths = freeze_baseline(TEMPLATES, STAND, out)
        self.assertTrue(paths)
        for path in paths:
            spec = ScenarioSpec.load(path)          # каждый файл — валидный сценарий
            self.assertTrue(spec.standard_refs)
            self.assertTrue(spec.remediation)

    def test_freeze_is_deterministic(self):
        a, b = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        freeze_baseline(TEMPLATES, STAND, a)
        freeze_baseline(TEMPLATES, STAND, b)
        names_a = sorted(p.name for p in a.glob("*.yaml"))
        names_b = sorted(p.name for p in b.glob("*.yaml"))
        self.assertEqual(names_a, names_b)
        for name in names_a:
            self.assertEqual((a / name).read_text(), (b / name).read_text())

    def test_required_minimum_frozen(self):
        out = Path(tempfile.mkdtemp())
        freeze_baseline(TEMPLATES, STAND, out)
        ids = {ScenarioSpec.load(p).id for p in out.glob("*.yaml")}
        for needed in ("bac-tool-argument-genai-invest-stand",
                       "memory-poisoning-to-tool-genai-invest-stand",
                       "system-prompt-leak-genai-invest-stand"):
            self.assertIn(needed, ids, needed)


class ShippedBaselineTests(unittest.TestCase):
    def test_shipped_baseline_loads(self):
        shipped = Path(__file__).resolve().parents[1] / "agentic_redteam" / "scenarios" / "baseline"
        specs = [ScenarioSpec.load(p) for p in sorted(shipped.glob("*.yaml"))]
        self.assertGreaterEqual(len(specs), 3)
