import unittest
from pathlib import Path
from agentic_redteam.generation.template import load_templates
from agentic_redteam.generation.composer import compose, Unsupported
from agentic_redteam.profile.schema import TargetProfile

ROOT = Path(__file__).resolve().parents[1] / "templates"
STAND = TargetProfile.load("tests/data/profile_stand.yaml")


class TemplateCatalogTests(unittest.TestCase):
    def setUp(self):
        self.templates = load_templates(ROOT)
        self.by_id = {t.id: t for t in self.templates}

    def test_required_minimum_present(self):
        for needed in ("bac-tool-argument", "memory-poisoning-to-tool",
                       "memory-poisoning-cross-session", "system-prompt-leak"):
            self.assertIn(needed, self.by_id, needed)

    def test_every_template_cites_a_standard(self):
        for t in self.templates:
            self.assertTrue(any(t.standard.get(k) for k in ("asi", "llm", "atlas")), t.id)

    def test_every_template_composes_on_the_stand(self):
        for t in self.templates:
            result = compose(t, STAND)
            self.assertNotIsInstance(result, Unsupported,
                                     f"{t.id}: {getattr(result, 'reason', '')}")

    def test_prompt_leak_ceiling_is_text_only(self):
        result = compose(self.by_id["system-prompt-leak"], STAND)
        self.assertEqual([a["type"] for a in result.goal], ["response_contains"])
