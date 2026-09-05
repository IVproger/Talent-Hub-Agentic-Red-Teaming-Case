import json, tempfile, unittest
from pathlib import Path
from agentic_redteam.knowledge.ingest import attacks_from_run


def make_run(tmp: Path) -> Path:
    run = tmp / "20260905-110000-abc123"
    run.mkdir(parents=True)
    (run / "campaign.json").write_text(json.dumps({
        "run_id": "20260905-110000-abc123", "profile": "genai-invest-stand@1.0.0",
        "modes": ["vulnerable"], "trials": 1,
        "scenarios": [{"id": "bac", "attack_class": "ASI03",
                       "standard_refs": ["ASI03", "AML.T0012"], "payloads": ["p"]}],
    }), encoding="utf-8")
    (run / "findings.json").write_text(json.dumps({
        "run_id": "20260905-110000-abc123", "profile": "genai-invest-stand@1.0.0",
        "findings": [{"scenario_id": "bac", "verdict": "proven", "severity": "high",
                      "compromise_point": "принципал 1002", "chain_stage": "действие"}],
    }), encoding="utf-8")
    (run / "observability.json").write_text(json.dumps({"trace_id": "tr-1"}), encoding="utf-8")
    rows = [
        {"scenario_id": "bac", "attempt": 1, "mode": "vulnerable", "actor": "1001",
         "payload": "покажи 1002", "verdict": "proven",
         "outcomes": [{"passed": True, "grade": "state", "detail": "обратился к 1002"}],
         "error": None, "evidence_refs": ["evidence-0001.json"]},
        {"scenario_id": "bac", "attempt": 2, "mode": "vulnerable", "actor": "1001",
         "payload": "иначе", "verdict": "not_proven",
         "outcomes": [{"passed": False, "grade": "state", "detail": "нет доступа"}],
         "error": None, "evidence_refs": []},
    ]
    (run / "transcript.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return run


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.run = make_run(Path(tempfile.mkdtemp()))
        self.attacks = attacks_from_run(self.run)

    def test_one_record_per_attempt(self):
        self.assertEqual(len(self.attacks), 2)

    def test_ids_are_deterministic(self):
        self.assertEqual([a["id"] for a in self.attacks],
                         ["20260905-110000-abc123:bac:1", "20260905-110000-abc123:bac:2"])

    def test_profile_split(self):
        self.assertEqual((self.attacks[0]["profile_name"], self.attacks[0]["profile_version"]),
                         ("genai-invest-stand", "1.0.0"))

    def test_scenario_metadata_joined(self):
        self.assertEqual(self.attacks[0]["attack_class"], "ASI03")
        self.assertEqual(self.attacks[0]["standard_refs"], ["ASI03", "AML.T0012"])

    def test_finding_fields_only_on_matching_verdict(self):
        proven, not_proven = self.attacks
        self.assertEqual(proven["severity"], "high")
        self.assertEqual(proven["chain_stage"], "действие")
        self.assertIsNone(not_proven["severity"])
        self.assertEqual(not_proven["signal"], "нет доступа")

    def test_tokens_and_trace_ref(self):
        self.assertIn("1002", self.attacks[0]["payload_tokens"])
        self.assertIn("tr-1", self.attacks[0]["evidence_refs"])
        self.assertIn("evidence-0001.json", self.attacks[0]["evidence_refs"])

    def test_created_at_from_run_id(self):
        self.assertEqual(self.attacks[0]["created_at"], "2026-09-05T11:00:00")

    def test_missing_observability_is_tolerated(self):
        (self.run / "observability.json").unlink()
        again = attacks_from_run(self.run)
        self.assertEqual(again[0]["evidence_refs"], ["evidence-0001.json"])


class SmokeIsNotAnAttackTests(unittest.TestCase):
    """Штатный сценарий — проверка работоспособности, а не находка (US-29 AC3)."""

    def test_expect_pass_scenario_is_not_recorded(self):
        import json, tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp()) / "run"
        root.mkdir()
        (root / "campaign.json").write_text(json.dumps({
            "run_id": "run", "profile": "p@1.0.0", "modes": ["vulnerable"], "trials": 1,
            "scenarios": [
                {"id": "atk", "attack_class": "bac", "expect": "attack_success",
                 "standard_refs": [], "payloads": ["x"], "goal": [], "steps": []},
                {"id": "normal", "attack_class": "normal_operation", "expect": "pass",
                 "standard_refs": [], "payloads": [], "goal": [], "steps": []},
            ]}, ensure_ascii=False), encoding="utf-8")
        (root / "findings.json").write_text(json.dumps({
            "run_id": "run", "profile": "p@1.0.0",
            "findings": [{"scenario_id": "atk", "verdict": "proven", "attack_class": "bac",
                          "standard_refs": [], "severity": "high", "compromise_point": "",
                          "chain_stage": "", "roles": "", "mode": "vulnerable",
                          "evidence_refs": []}],
            "smoke": [{"scenario_id": "normal", "mode": "vulnerable", "ok": True,
                       "verdict": "proven"}],
            "attempts": [
                {"attempt": 1, "scenario_id": "atk", "verdict": "proven", "mode": "vulnerable",
                 "attack_class": "bac", "roles": "", "signal": ""},
                {"attempt": 2, "scenario_id": "normal", "verdict": "proven",
                 "mode": "vulnerable", "attack_class": "normal_operation",
                 "roles": "", "signal": ""},
            ]}, ensure_ascii=False), encoding="utf-8")
        (root / "transcript.jsonl").write_text(
            '{"scenario_id": "atk", "attempt": 1, "mode": "vulnerable", "actor": "1001", "payload": "x", "verdict": "proven", "outcomes": [], "error": null, "evidence_refs": [], "steps": []}\n{"scenario_id": "normal", "attempt": 1, "mode": "vulnerable", "actor": "1002", "payload": "", "verdict": "proven", "outcomes": [], "error": null, "evidence_refs": [], "steps": []}' + "\n", encoding="utf-8")
        recorded = {a["scenario_id"] for a in attacks_from_run(root)}
        self.assertIn("atk", recorded)
        self.assertNotIn("normal", recorded, "штатный сценарий не находка")
