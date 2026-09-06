import json
import tempfile
import unittest
from pathlib import Path

import yaml

from agentic_redteam.profile.ingest import build_draft
from tests.fakes import FakeLLM


class ProfileIngestTests(unittest.TestCase):
    def _openapi(self) -> Path:
        root = Path(tempfile.mkdtemp())
        path = root / "openapi.json"
        path.write_text(json.dumps({
            "openapi": "3.0.0",
            "paths": {
                "/orders": {
                    "post": {
                        "operationId": "create_order",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Order"}
                                }
                            }
                        },
                    }
                }
            },
            "components": {
                "schemas": {
                    "Order": {
                        "type": "object",
                        "properties": {"account_id": {"type": "string"}},
                    }
                }
            },
        }), encoding="utf-8")
        return path

    def test_openapi_and_documents_become_a_review_gated_draft(self):
        openapi = self._openapi()
        system_card = openapi.parent / "system-card.md"
        system_card.write_text("Uses a long-lived memory store.", encoding="utf-8")
        draft = build_draft(
            openapi, "http://localhost:7001", "target", documents=[system_card]
        )
        self.assertEqual(draft["surface"]["tools"][0]["args"], ["account_id"])
        self.assertTrue(draft["entrypoint"]["review_required"])
        self.assertEqual(len(draft["ingest"]["sources"]), 2)
        self.assertNotIn("text", draft["ingest"]["sources"][1])
        self.assertEqual(len(draft["ingest"]["sources"][1]["sha256"]), 64)

    def test_reviewed_bindings_are_merged_without_becoming_hypotheses(self):
        openapi = self._openapi()
        bindings = openapi.parent / "bindings.yaml"
        bindings.write_text(yaml.safe_dump({
            "entrypoint": {"review_required": []},
            "surface": {"tools": [{
                "name": "create_order", "args": ["account_id"], "sensitive": True,
                "principal_from": {"kind": "argument", "name": "account_id"},
            }]},
        }), encoding="utf-8")
        draft = build_draft(
            openapi, "http://localhost:7001", "target", bindings=bindings
        )
        self.assertEqual(draft["entrypoint"]["review_required"], [])
        self.assertTrue(draft["surface"]["tools"][0]["sensitive"])


    def test_judge_accepts_bindings_into_profile_without_human(self):
        openapi = self._openapi()
        system_card = openapi.parent / "system-card.md"
        system_card.write_text(
            "create_order reads a client's data by account_id.", encoding="utf-8"
        )
        analyst = FakeLLM([json.dumps({
            "tools": [{"name": "create_order", "sensitive": True,
                       "principal_from": {"kind": "argument", "name": "account_id"}}],
            "memory": [{"id": "notes", "scope": "cross_user"}],
        })])
        judge = FakeLLM([json.dumps({
            "accepted": {"surface": {"tools": [{
                "name": "create_order", "args": ["account_id"], "sensitive": True,
                "principal_from": {"kind": "argument", "name": "account_id"},
            }]}},
            "rejected": [{"binding": "memory notes scope=cross_user",
                          "reason": "scope не подтверждён прозой документа"}],
            "confidence": {"create_order.sensitive": 0.9},
        })])
        draft = build_draft(
            openapi, "http://localhost:7001", "target",
            documents=[system_card], analyst=analyst, judge=judge,
        )
        # accepted binding is applied into the profile itself, not left in limbo
        tool = draft["surface"]["tools"][0]
        self.assertTrue(tool["sensitive"])
        self.assertEqual(
            tool["principal_from"], {"kind": "argument", "name": "account_id"}
        )
        # rejected binding is recorded with its reason and NOT applied
        self.assertEqual(draft["surface"]["memory"], [])
        rejected = draft["ingest"]["judgement"]["rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertIn("scope", rejected[0]["reason"])
        # provenance is explicit: llm-judged, never silently state-confirmed
        self.assertEqual(draft["ingest"]["judgement"]["provenance"], "llm-judged")



    def test_judge_binding_that_breaks_schema_is_rejected_not_fatal(self):
        from agentic_redteam.profile.schema import TargetProfile
        openapi = self._openapi()
        analyst = FakeLLM([json.dumps({
            "tools": [{"name": "create_order", "sensitive": True}],
        })])
        judge = FakeLLM([json.dumps({
            "accepted": {
                "surface": {"tools": [{
                    "name": "create_order", "args": ["account_id"], "sensitive": True,
                    "principal_from": {"kind": "argument", "name": "account_id"},
                }]},
                "isolation": {"broken": "not a list"},
            },
            "rejected": [],
            "confidence": {},
        })])
        draft = build_draft(
            openapi, "http://localhost:7001", "target",
            analyst=analyst, judge=judge,
        )
        # the well-formed binding is applied
        self.assertTrue(draft["surface"]["tools"][0]["sensitive"])
        # the schema-breaking binding is NOT applied: isolation stays a list
        self.assertIsInstance(draft["isolation"], list)
        # the draft as a whole stays schema-valid (init does not crash)
        TargetProfile.from_mapping(draft)
        # the bad binding is recorded as rejected, with a schema reason
        rejected = draft["ingest"]["judgement"]["rejected"]
        self.assertTrue(any("isolation" in str(r.get("binding")) for r in rejected))



    def test_ingest_prompts_cover_identities_and_entrypoint_for_runnable_draft(self):
        openapi = self._openapi()
        captured = {}

        class Capturing:
            def __init__(self, role, reply):
                self.role, self.reply = role, reply

            def complete(self, prompt):
                captured[self.role] = prompt
                return self.reply

        analyst = Capturing("analyst", json.dumps({"tools": []}))
        judge = Capturing("judge", json.dumps(
            {"accepted": {}, "rejected": [], "confidence": {}}))
        build_draft(
            openapi, "http://localhost:7001", "target",
            analyst=analyst, judge=judge,
        )
        # onboarding must be able to bind the runnable, load-bearing sections,
        # not just the surface — otherwise a docs-built profile cannot execute.
        for section in ("identities", "entrypoint"):
            self.assertIn(section, captured["analyst"])
            self.assertIn(section, captured["judge"])
        # the onboarding prompt must be target-agnostic: no stand-specific
        # identifiers baked in — it works for any target from its documents.
        for token in ("agent_policy_memories", "invest-server", "8600",
                      "genai-invest"):
            self.assertNotIn(token, captured["analyst"].lower())
            self.assertNotIn(token, captured["judge"].lower())



    def test_ingest_prompt_carries_profile_schema_for_conformant_bindings(self):
        openapi = self._openapi()
        captured = {}

        class Cap:
            def __init__(self, role, reply):
                self.role, self.reply = role, reply

            def complete(self, prompt):
                captured[self.role] = prompt
                return self.reply

        build_draft(
            openapi, "http://localhost:7001", "target",
            analyst=Cap("analyst", json.dumps({"tools": []})),
            judge=Cap("judge", json.dumps(
                {"accepted": {}, "rejected": [], "confidence": {}})),
        )
        # the prompt must carry the exact profile schema vocabulary so the LLM
        # emits schema-conformant bindings instead of guessing shapes.
        for token in ("docker-exec-mint", "db-query", "cross_user",
                      "per_deployment", "commit_memory"):
            self.assertIn(token, captured["analyst"])
            self.assertIn(token, captured["judge"])



    def test_analyst_transient_bad_response_is_retried(self):
        openapi = self._openapi()
        # first completion is garbage (flaky provider), retry yields valid JSON
        analyst = FakeLLM(["oops не json", json.dumps({"tools": []})])
        judge = FakeLLM([json.dumps(
            {"accepted": {}, "rejected": [], "confidence": {}})])
        draft = build_draft(
            openapi, "http://localhost:7001", "target",
            analyst=analyst, judge=judge,
        )
        # retry recovered: hypotheses parsed, judgement produced
        self.assertEqual(draft["ingest"]["judgement"]["provenance"], "llm-judged")



    def test_repair_makes_judged_draft_runnable(self):
        from agentic_redteam.profile.schema import TargetProfile
        openapi = self._openapi()
        analyst = FakeLLM([json.dumps({"tools": []})])
        judge = FakeLLM([json.dumps({"accepted": {
            "entrypoint": {"commit_memory": {"path": "/f", "method": "POST",
                                             "response": {"path": "x"}}},
            "evidence": [
                {"id": "good", "provider": "http-canary", "config": {"bind": "127.0.0.1:0"}},
                {"id": "bad", "provider": "db-query", "config": {"collection": "c"}},
            ],
            "junk_note": "should be dropped",
        }, "rejected": [], "confidence": {}})])
        draft = build_draft(openapi, "http://localhost:7001", "target",
                            analyst=analyst, judge=judge)
        # invented top-level key dropped (recorded, not silently kept)
        self.assertNotIn("junk_note", draft)
        # LLM judge is the review — the human gate it covered is cleared
        self.assertNotIn("review_required", draft["entrypoint"])
        # incomplete evidence provider dropped; complete one kept
        ids = [e["id"] for e in draft["evidence"]]
        self.assertIn("good", ids)
        self.assertNotIn("bad", ids)
        rejected = draft["ingest"]["judgement"]["rejected"]
        self.assertTrue(any("bad" in str(r.get("binding")) for r in rejected))
        # the repaired draft loads as a profile
        TargetProfile.from_mapping(draft)



    def test_repair_drops_evidence_the_engine_cannot_construct(self):
        openapi = self._openapi()
        analyst = FakeLLM([json.dumps({"tools": []})])
        judge = FakeLLM([json.dumps({"accepted": {"evidence": [
            {"id": "reset", "provider": "state-reset",
             "config": {"compose_file": "x", "redis": {"service": "r"}}},
        ]}, "rejected": [], "confidence": {}})])
        draft = build_draft(openapi, "http://localhost:7001", "target",
                            analyst=analyst, judge=judge)
        # state-reset без redis.key_patterns движок не соберёт → отброшен
        self.assertEqual(draft["evidence"], [])
        self.assertTrue(any("reset" in str(r.get("binding"))
                            for r in draft["ingest"]["judgement"]["rejected"]))



    def test_repair_drops_trace_with_bad_host(self):
        openapi = self._openapi()
        analyst = FakeLLM([json.dumps({"tools": []})])
        judge = FakeLLM([json.dumps({"accepted": {"evidence": [
            {"id": "ok", "provider": "http-canary", "config": {"bind": "127.0.0.1:0"}},
            {"id": "bad-trace", "provider": "trace", "config": {"host": "<url>"}},
        ]}, "rejected": [], "confidence": {}})])
        draft = build_draft(openapi, "http://localhost:7001", "target",
                            analyst=analyst, judge=judge)
        ids = [e["id"] for e in draft["evidence"]]
        self.assertIn("ok", ids)
        self.assertNotIn("bad-trace", ids)



if __name__ == "__main__":
    unittest.main()
