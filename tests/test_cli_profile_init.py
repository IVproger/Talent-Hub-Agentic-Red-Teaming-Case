"""profile init: структура из OpenAPI детерминированно, семантика — гипотезы."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import yaml

import unittest.mock

from agentic_redteam.app_cli import main
from agentic_redteam.profile.schema import TargetProfile
from tests.fakes import FakeLLM


OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Invest API", "version": "2.1.0"},
    "paths": {
        "/clients/{cus}/portfolio": {
            "get": {
                "operationId": "get_portfolio",
                "parameters": [
                    {"name": "cus", "in": "path", "required": True},
                    {"name": "period", "in": "query"},
                ],
            }
        },
        "/healthz": {"get": {"operationId": "healthcheck", "parameters": []}},
        "/orders": {
            "post": {
                "parameters": [{"name": "account_id", "in": "query"}],
            }
        },
    },
}


def write_spec(document=None) -> str:
    path = Path(tempfile.mkdtemp()) / "openapi.json"
    path.write_text(json.dumps(document or OPENAPI), encoding="utf-8")
    return str(path)


def run_cli(*argv) -> tuple[int, str]:
    output, errors = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = main(list(argv))
    return code, output.getvalue() + errors.getvalue()


class ProfileInitTests(unittest.TestCase):
    def _draft(self, *extra) -> tuple[str, dict]:
        target = Path(tempfile.mkdtemp()) / "draft.yaml"
        code, out = run_cli("profile", "init", "--openapi", write_spec(),
                            "--base-url", "http://localhost:8600",
                            "--offline", "-o", str(target), *extra)
        self.assertEqual(code, 0, out)
        text = target.read_text(encoding="utf-8")
        return text, yaml.safe_load(text)

    def test_structure_comes_from_the_document(self):
        _, draft = self._draft()
        self.assertEqual(draft["entrypoint"]["base_url"], "http://localhost:8600")
        tools = {tool["name"]: tool for tool in draft["surface"]["tools"]}
        self.assertEqual(sorted(tools), ["get_portfolio", "healthcheck", "post_orders"])
        self.assertEqual(tools["get_portfolio"]["args"], ["cus", "period"])
        self.assertEqual(tools["healthcheck"]["args"], [])

    def test_principal_is_a_named_hypothesis_not_a_fact(self):
        text, draft = self._draft()
        tools = {tool["name"]: tool for tool in draft["surface"]["tools"]}
        self.assertEqual(tools["get_portfolio"]["principal_from"],
                         {"kind": "argument", "name": "cus"})
        self.assertEqual(tools["post_orders"]["principal_from"],
                         {"kind": "argument", "name": "account_id"})
        self.assertEqual(tools["healthcheck"]["principal_from"], {"kind": "none"})
        self.assertIn("TODO", text)
        self.assertIn("get_portfolio", text.split("name:")[0])   # гипотезы в шапке

    def test_draft_loads_as_a_profile(self):
        target = Path(tempfile.mkdtemp()) / "draft.yaml"
        code, out = run_cli("profile", "init", "--openapi", write_spec(),
                            "--base-url", "http://localhost:8600", "--offline",
                            "--name", "invest", "--version", "0.2.0", "-o", str(target))
        self.assertEqual(code, 0, out)
        profile = TargetProfile.load(target)
        self.assertEqual((profile.name, profile.version), ("invest", "0.2.0"))
        self.assertEqual(profile.tools[0].principal_from["kind"], "argument")

    def test_name_defaults_to_the_document_title(self):
        _, draft = self._draft()
        self.assertEqual(draft["name"], "invest-api")

    def test_header_lists_what_a_human_must_still_declare(self):
        text, _ = self._draft()
        for section in ("памят", "изоляц", "evidence", "личност"):
            self.assertIn(section, text.lower())

    def test_without_offline_the_llm_path_is_named_not_faked(self):
        code, out = run_cli("profile", "init", "--openapi", write_spec(),
                            "--base-url", "http://localhost:8600")
        self.assertEqual(code, 2)
        self.assertIn("--offline", out)

    def test_unreadable_document_is_a_configuration_error(self):
        code, out = run_cli("profile", "init", "--openapi", "нет-такого.json",
                            "--base-url", "http://localhost:8600", "--offline", "--json")
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["ok"])

    def test_stdout_when_no_output_file(self):
        code, out = run_cli("profile", "init", "--openapi", write_spec(),
                            "--base-url", "http://localhost:8600", "--offline")
        self.assertEqual(code, 0)
        self.assertIn("get_portfolio", out)


    def test_judge_path_applies_bindings_and_records_provenance(self):
        analyst_out = json.dumps({
            "tools": [{"name": "get_portfolio", "sensitive": True}],
        })
        judge_out = json.dumps({
            "accepted": {"entrypoint": {"review_required": ["осталась только память"]}},
            "rejected": [{"binding": "get_portfolio.sensitive",
                          "reason": "прямо в документе не сказано"}],
            "confidence": {},
        })
        clients = iter([FakeLLM([analyst_out]), FakeLLM([judge_out])])
        target = Path(tempfile.mkdtemp()) / "draft.yaml"
        with unittest.mock.patch(
            "agentic_redteam.app_cli.make_llm_client",
            side_effect=lambda *a, **k: next(clients),
        ):
            code, out = run_cli("profile", "init", "--openapi", write_spec(),
                                "--base-url", "http://localhost:8600",
                                "-o", str(target))
        self.assertEqual(code, 0, out)
        draft = yaml.safe_load(target.read_text(encoding="utf-8"))
        # judge-accepted fragment merged into the profile itself
        self.assertEqual(draft["entrypoint"]["review_required"],
                         ["осталась только память"])
        # verdict recorded with explicit, honest provenance
        judgement = draft["ingest"]["judgement"]
        self.assertEqual(judgement["provenance"], "llm-judged")
        self.assertEqual(len(judgement["rejected"]), 1)



    def test_init_accepts_arbitrary_wiring_documents(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        doc1 = d / "compose.yml"; doc1.write_text("service: db", encoding="utf-8")
        doc2 = d / "schema.md"; doc2.write_text("collection notes", encoding="utf-8")
        target = d / "draft.yaml"
        code, out = run_cli("profile", "init", "--openapi", write_spec(),
                            "--base-url", "http://localhost:8600", "--offline",
                            "--doc", str(doc1), "--doc", str(doc2), "-o", str(target))
        self.assertEqual(code, 0, out)
        draft = yaml.safe_load(target.read_text(encoding="utf-8"))
        paths = [Path(s["path"]).name for s in draft["ingest"]["sources"]]
        self.assertIn("compose.yml", paths)
        self.assertIn("schema.md", paths)



if __name__ == "__main__":
    unittest.main()
