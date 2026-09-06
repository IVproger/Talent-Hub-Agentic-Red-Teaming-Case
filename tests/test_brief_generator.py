from __future__ import annotations

import json
import unittest
from pathlib import Path

from agentic_redteam.attacker.brief_generator import (
    generate_briefs,
    profile_digest,
)
from agentic_redteam.attacker.standards import standard_items
from agentic_redteam.errors import PipelineConfigurationError
from tests.test_attack_briefs import brief, stand_profile


class ScriptedLLM:
    def __init__(self, output):
        self.output = output
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append(prompt)
        return self.output


class ProfileDigestTests(unittest.TestCase):
    def test_digest_contains_only_profile_entities(self):
        digest = profile_digest(stand_profile())
        self.assertEqual(
            digest["roles"], {"attacker": {"cus": "1001"}, "victim": {"cus": "1002"}}
        )
        self.assertEqual(digest["tools"][0]["name"], "get_portfolio")
        self.assertEqual([b["id"] for b in digest["boundaries"]], ["user", "session"])
        self.assertTrue(digest["supports_memory_commit"])
        self.assertIn("vulnerable", digest["modes"])


class StandardsCatalogTests(unittest.TestCase):
    def test_sources_and_ref_binding(self):
        items = standard_items(("owasp-llm", "owasp-agentic"))
        self.assertEqual(len(items), 20)
        by_ref = {item["ref"]: item for item in items}
        self.assertIn("OWASP Top 10 for Agentic Applications", by_ref["ASI03"]["source"])
        self.assertIn("OWASP Top 10 for LLM Applications", by_ref["LLM08"]["source"])

    def test_atlas_is_opt_in(self):
        self.assertEqual(len(standard_items(("owasp-llm",))), 10)
        rows = standard_items(("atlas",))
        self.assertEqual(rows[0]["ref"], "AML.Txxxx")

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            standard_items(("owasp-llm", "cis"))


class GenerateBriefsTests(unittest.TestCase):
    def test_ideas_do_not_bypass_profile_validation(self):
        llm = ScriptedLLM(json.dumps([
            brief(id='bad', objective='Прочитать get_portfolio(cus=9999).'), brief(),
        ]))
        result = generate_briefs(stand_profile(), llm, ideas=['Использовать cus=9999'])
        self.assertEqual(len(result.briefs), 1)
        self.assertEqual(len(result.rejected), 1)

    def test_empty_idea_rejected_without_llm_call(self):
        llm = ScriptedLLM('[]')
        with self.assertRaisesRegex(PipelineConfigurationError, '--idea'):
            generate_briefs(stand_profile(), llm, ideas=['\n'])
        self.assertEqual(llm.prompts, [])

    def test_generates_valid_briefs_from_llm_json(self):
        profile = stand_profile()
        llm = ScriptedLLM(json.dumps([brief()], ensure_ascii=False))
        result = generate_briefs(profile, llm, count=1)
        self.assertEqual(len(result.briefs), 1)
        self.assertEqual(result.briefs[0].id, "cross-client-portfolio-access")
        self.assertEqual(result.rejected, [])
        # Профиль и стандарты попадают в промпт генератора.
        prompt = llm.prompts[0]
        self.assertIn("get_portfolio", prompt)
        self.assertIn("ASI03", prompt)
        self.assertIn("LLM01", prompt)

    def test_invalid_briefs_are_rejected_with_reasons(self):
        profile = stand_profile()
        payload = json.dumps([
            brief(),                                        # валидный
            brief(id="bad-ref", standard_refs=["ASI99"]),   # неизвестная ссылка
            brief(id="bad-principal",
                  objective="Прочитать портфель cus=9999 из сессии cus=1001."),
            {"id": "no-fields"},
        ], ensure_ascii=False)
        result = generate_briefs(profile, ScriptedLLM(payload), count=5)
        self.assertEqual([b.id for b in result.briefs], ["cross-client-portfolio-access"])
        self.assertEqual(len(result.rejected), 3)
        self.assertTrue(all("reason" in row for row in result.rejected))

    def test_no_valid_briefs_is_configuration_error(self):
        profile = stand_profile()
        payload = json.dumps([brief(id="bad", standard_refs=["XXX"])])
        with self.assertRaises(PipelineConfigurationError):
            generate_briefs(profile, ScriptedLLM(payload), count=3)

    def test_non_json_output_is_configuration_error(self):
        with self.assertRaises(PipelineConfigurationError):
            generate_briefs(stand_profile(), ScriptedLLM("нет JSON"), count=1)

    def test_count_caps_the_result(self):
        payload = json.dumps([brief(), brief(id="second-brief")])
        result = generate_briefs(stand_profile(), ScriptedLLM(payload), count=1)
        self.assertEqual(len(result.briefs), 1)


if __name__ == "__main__":
    unittest.main()
