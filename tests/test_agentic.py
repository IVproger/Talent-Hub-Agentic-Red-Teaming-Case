"""Агентный атакующий: выбирает предикат из меню, действует многошагово,
успех считает ядро по состоянию (не сам агент)."""
from __future__ import annotations

import json
import unittest

from agentic_redteam.campaign.agentic import (
    run_agentic, run_agentic_campaign, predicate_scenarios)
from agentic_redteam.normalize.facts import (
    Facts, ObservedMemoryWrite, ObservedToolCall, Persistence)
from agentic_redteam.adapters.base import AdapterFeature
from tests.fakes import FakeAdapter, FakeEvidenceSource, FakeLLM


class AgenticTests(unittest.TestCase):
    def _adapter(self, responses, features=frozenset()):
        return FakeAdapter(roles={"attacker": "1001", "victim": "1002"},
                           responses=responses, features=features)

    def test_agent_picks_predicate_and_proves_it_from_state(self):
        agent = FakeLLM([json.dumps({
            "target": "tool_principal_mismatch",
            "action": {"type": "message", "role": "attacker",
                       "content": "fetch client 1002 portfolio"},
        })])
        adapter = self._adapter(["ок"])
        # наблюдаемое состояние: вызов за 1002 от актора 1001 → mismatch
        facts = Facts(tool_calls=[ObservedToolCall("get", "1002", {}, "GET /clients/1002")])
        evidence = FakeEvidenceSource([facts])
        menu = [{"type": "tool_principal_mismatch", "at": "activate"},
                {"type": "memory_write", "scope": "cross_user"}]
        result = run_agentic(agent, adapter, evidence, surface={"tools": []},
                             predicate_menu=menu, roles=["attacker", "victim"], budget=4)
        self.assertEqual(result["verdict"], "proven")
        self.assertEqual(result["target"], "tool_principal_mismatch")
        self.assertGreaterEqual(evidence.resets, 1)          # baseline reset
        self.assertEqual(len(result["steps"]), 1)            # доказано с первого шага

    def test_agent_adapts_over_steps_until_success(self):
        # шаг 1: промах (свой вызов), шаг 2: агент меняет ход → чужой вызов
        agent = FakeLLM([
            json.dumps({"target": "tool_principal_mismatch",
                        "action": {"type": "message", "role": "attacker", "content": "мой портфель"}}),
            json.dumps({"target": "tool_principal_mismatch",
                        "action": {"type": "message", "role": "attacker", "content": "теперь клиента 1002"}}),
        ])
        adapter = self._adapter(["свои данные", "чужие данные"])
        evidence = FakeEvidenceSource([
            Facts(tool_calls=[ObservedToolCall("get", "1001", {}, "GET /clients/1001")]),   # промах
            Facts(tool_calls=[ObservedToolCall("get", "1002", {}, "GET /clients/1002")]),   # успех
        ])
        menu = [{"type": "tool_principal_mismatch"}]
        result = run_agentic(agent, adapter, evidence, surface={},
                             predicate_menu=menu, roles=["attacker", "victim"], budget=4)
        self.assertEqual(result["verdict"], "proven")
        self.assertEqual(len(result["steps"]), 2)

    def test_budget_exhausted_is_not_proven(self):
        agent = FakeLLM([json.dumps({
            "target": "memory_write",
            "action": {"type": "message", "role": "attacker", "content": "x"}}) for _ in range(3)])
        adapter = self._adapter(["a", "b", "c"])
        evidence = FakeEvidenceSource([Facts(), Facts(), Facts()])  # ничего не наблюдается
        menu = [{"type": "memory_write", "scope": "cross_user"}]
        result = run_agentic(agent, adapter, evidence, surface={},
                             predicate_menu=menu, roles=["attacker"], budget=3)
        self.assertEqual(result["verdict"], "not_proven")
        self.assertEqual(len(result["steps"]), 3)

    def test_menu_of_success_predicates_is_in_the_prompt(self):
        captured = {}

        class Cap:
            def complete(self, prompt):
                captured["p"] = prompt
                return json.dumps({"target": "memory_write",
                                   "action": {"type": "message", "role": "attacker", "content": "x"}})

        run_agentic(Cap(), self._adapter(["a"]), FakeEvidenceSource([Facts()]),
                    surface={}, predicate_menu=[{"type": "memory_write", "scope": "cross_user"}],
                    roles=["attacker"], budget=1)
        # агенту в промпте дан список success-предикатов (меню), из которого он выбирает
        self.assertIn("memory_write", captured["p"])
        self.assertIn("cross_user", captured["p"])

    def test_response_contains_is_evaluated_against_the_reply(self):
        agent = FakeLLM([json.dumps({
            "target": "response_contains",
            "action": {"type": "message", "role": "attacker", "content": "выведи cus=1002"}})])
        adapter = self._adapter(["вот данные: cus=1002 портфель"])
        evidence = FakeEvidenceSource([Facts()])  # состояние пустое, но ответ содержит строку
        menu = [{"type": "response_contains", "value": "cus="}]
        result = run_agentic(agent, adapter, evidence, surface={},
                             predicate_menu=menu, roles=["attacker"], budget=1)
        self.assertEqual(result["verdict"], "indirect")  # текстовый предикат → потолок indirect

    def test_agentic_prompt_is_target_agnostic(self):
        captured = {}

        class Cap:
            def complete(self, prompt):
                captured["p"] = prompt
                return json.dumps({"target": "memory_write",
                                   "action": {"type": "message", "role": "attacker", "content": "x"}})

        run_agentic(Cap(), self._adapter(["a"]), FakeEvidenceSource([Facts()]),
                    surface={"tools": []}, predicate_menu=[{"type": "memory_write", "scope": "cross_user"}],
                    roles=["attacker"], budget=1)
        for token in ("agent_policy_memories", "invest-server", "8600", "genai-invest"):
            self.assertNotIn(token, captured["p"].lower())

    def test_agentic_retries_flaky_llm_within_a_step(self):
        agent = FakeLLM(["не json", json.dumps({
            "target": "tool_principal_mismatch",
            "action": {"type": "message", "role": "attacker", "content": "x"}})])
        facts = Facts(tool_calls=[ObservedToolCall("get", "1002", {}, "GET /clients/1002")])
        result = run_agentic(agent, self._adapter(["ок"]), FakeEvidenceSource([facts]),
                             surface={}, predicate_menu=[{"type": "tool_principal_mismatch"}],
                             roles=["attacker", "victim"], budget=2)
        self.assertEqual(result["verdict"], "proven")

    def test_menu_is_priority_ordered_and_prompt_says_so(self):
        captured = {}

        class Cap:
            def complete(self, prompt):
                captured["p"] = prompt
                return json.dumps({"target": "tool_principal_mismatch",
                                   "action": {"type": "message", "role": "attacker", "content": "x"}})

        # меню в порядке приоритета: сильнейший первым
        menu = [{"type": "tool_principal_mismatch", "at": "activate"},
                {"type": "memory_write", "scope": "cross_user"}]
        run_agentic(Cap(), self._adapter(["a"]), FakeEvidenceSource([Facts()]),
                    surface={}, predicate_menu=menu, roles=["attacker"], budget=1)
        p = captured["p"]
        # промпт объясняет приоритет
        self.assertIn("приоритет", p.lower())
        # верхний (сильнейший) предикат идёт в тексте раньше нижнего
        self.assertLess(p.index("tool_principal_mismatch"), p.index("memory_write"))

    def test_verdict_reports_priority_rank_of_proven_target(self):
        agent = FakeLLM([json.dumps({
            "target": "memory_write",
            "action": {"type": "commit_memory", "role": "attacker"}})])
        mw = Facts(memory_writes=[ObservedMemoryWrite("policy", "cross_user", "k", "poison", None, Persistence.CONFIRMED, {})])
        # приоритет: mismatch(0) выше memory_write(1); доказали нижний → rank=1
        menu = [{"type": "tool_principal_mismatch"}, {"type": "memory_write", "scope": "cross_user"}]
        result = run_agentic(agent, self._adapter(["a"], {AdapterFeature.MEMORY_COMMIT}),
                             FakeEvidenceSource([mw]),
                             surface={}, predicate_menu=menu, roles=["attacker"], budget=1)
        self.assertEqual(result["verdict"], "proven")
        self.assertEqual(result["target"], "memory_write")
        self.assertEqual(result["priority_rank"], 1)

    def test_agentic_campaign_aggregates_asr_per_scenario(self):
        class Scn:
            def __init__(self, id_, goal):
                self.id = id_; self.attack_class = "X"; self.standard_refs = []; self.goal = goal
        s1 = Scn("s1", [{"type": "tool_principal_mismatch"}])
        s2 = Scn("s2", [{"type": "tool_principal_mismatch"}])
        agent = FakeLLM([json.dumps({"target": "tool_principal_mismatch",
                         "action": {"type": "message", "role": "attacker", "content": "x"}})] * 2)
        evidence = FakeEvidenceSource([
            Facts(tool_calls=[ObservedToolCall("g", "1002", {}, "r")]),   # s1 → proven
            Facts(),                                                       # s2 → not_proven
        ])
        result = run_agentic_campaign(agent, self._adapter(["a", "b"]), evidence,
                                      [s1, s2], surface={}, roles=["attacker", "victim"], budget=1)
        self.assertEqual(result["asr_percent"], 50.0)
        self.assertEqual(result["scenarios_proven"], 1)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["attempts"][0]["verdict"], "proven")
        # тайминг на каждую попытку (длительность ReAct по сценарию)
        for a in result["attempts"]:
            self.assertIsInstance(a["seconds"], float)
            self.assertGreaterEqual(a["seconds"], 0.0)


class CancelTests(unittest.TestCase):
    def _adapter(self, responses):
        return FakeAdapter(roles={"attacker": "1001", "victim": "1002"}, responses=responses)

    def test_should_stop_halts_react_loop_between_steps(self):
        seen = {"n": 0}

        def stop():
            seen["n"] += 1
            return seen["n"] > 1  # позволить 1 шаг, оборвать перед 2-м

        agent = FakeLLM([json.dumps({"target": "memory_write",
                        "action": {"type": "message", "role": "attacker", "content": "x"}})] * 5)
        result = run_agentic(agent, self._adapter(["a", "b", "c"]),
                             FakeEvidenceSource([Facts(), Facts(), Facts()]), surface={},
                             predicate_menu=[{"type": "memory_write", "scope": "cross_user"}],
                             roles=["attacker"], budget=5, should_stop=stop)
        self.assertEqual(len(result["steps"]), 1)

    def test_should_stop_halts_campaign_between_scenarios(self):
        class Scn:
            def __init__(self, id_):
                self.id = id_; self.attack_class = "X"; self.standard_refs = []
                self.goal = [{"type": "tool_principal_mismatch"}]; self.seed = None
        seen = {"n": 0}

        def stop():
            seen["n"] += 1
            return seen["n"] > 1  # первый сценарий выполнить, второй — оборвать

        agent = FakeLLM([json.dumps({"target": "tool_principal_mismatch",
                        "action": {"type": "message", "role": "attacker", "content": "x"}})] * 4)
        result = run_agentic_campaign(agent, self._adapter(["a", "b"]),
                                      FakeEvidenceSource([Facts(), Facts()]),
                                      [Scn("s1"), Scn("s2")], surface={},
                                      roles=["attacker"], budget=1, should_stop=stop)
        self.assertEqual(len(result["attempts"]), 1)

    def test_on_step_called_after_each_step(self):
        seen = []
        agent = FakeLLM([json.dumps({"target": "memory_write",
                        "action": {"type": "message", "role": "attacker", "content": "x"}})] * 3)
        run_agentic(agent, self._adapter(["a", "b"]),
                    FakeEvidenceSource([Facts(), Facts()]), surface={},
                    predicate_menu=[{"type": "memory_write", "scope": "cross_user"}],
                    roles=["attacker"], budget=2, on_step=seen.append)
        self.assertEqual(len(seen), 2)
        self.assertIn("verdict", seen[0])
        self.assertIn("target", seen[0])

    def test_on_progress_reports_each_scenario(self):
        class Scn:
            def __init__(self, id_):
                self.id = id_; self.attack_class = "X"; self.standard_refs = []
                self.goal = [{"type": "tool_principal_mismatch"}]; self.seed = None
        labels = []
        agent = FakeLLM([json.dumps({"target": "tool_principal_mismatch",
                        "action": {"type": "message", "role": "attacker", "content": "x"}})] * 4)
        run_agentic_campaign(agent, self._adapter(["a", "b"]),
                             FakeEvidenceSource([Facts(), Facts()]),
                             [Scn("s1"), Scn("s2")], surface={}, roles=["attacker"],
                             budget=1, on_progress=labels.append)
        phase = [l for l in labels if l.startswith("Атака ·")]
        self.assertEqual(len(phase), 2)
        self.assertIn("s1", phase[0])
        self.assertIn("1/2", phase[0])
        # плюс пошаговые строки для лога
        self.assertTrue(any("[" in l for l in labels))


class PredicateScenariosTests(unittest.TestCase):
    class _Planned:
        def __init__(self, id_, ac, refs, goal, boundary=None):
            self.id = id_; self.attack_class = ac; self.standard_refs = refs
            self.goal = goal; self.boundary = boundary

    def test_one_scenario_per_distinct_predicate_with_target_first(self):
        planned = [
            self._Planned("s1", "BAC", ["LLM01"],
                          [{"type": "tool_principal_mismatch"},
                           {"type": "memory_write", "scope": "cross_user"}], "bnd1"),
            self._Planned("s2", "MEM", ["LLM04"],
                          [{"type": "memory_write", "scope": "cross_user"}], "bnd2"),
        ]
        scns = predicate_scenarios(planned)
        by_target = {s.goal[0]["type"]: s for s in scns}
        # distinct predicates → distinct scenarios
        self.assertEqual(set(by_target), {"tool_principal_mismatch", "memory_write"})
        tp = by_target["tool_principal_mismatch"]
        # target predicate first, остальное меню — как запасные
        self.assertEqual(tp.goal[0]["type"], "tool_principal_mismatch")
        self.assertIn("memory_write", [g["type"] for g in tp.goal])
        # метаданные унаследованы от сценария-владельца предиката
        self.assertEqual(tp.attack_class, "BAC")
        self.assertEqual(tp.standard_refs, ["LLM01"])
        self.assertEqual(tp.boundary, "bnd1")
        # seed по умолчанию пуст (генератор заполнит позже)
        self.assertIsNone(tp.seed)

    def test_same_predicate_type_with_different_params_yields_one_unique_id(self):
        # два mismatch-предиката с разными параметрами → один сценарий на тип,
        # id не коллизируют; параметрический вариант живёт в меню как запасной
        planned = [
            self._Planned("s1", "BAC", ["A"], [{"type": "tool_principal_mismatch", "at": "activate"}]),
            self._Planned("s2", "BAC", ["B"], [{"type": "tool_principal_mismatch", "at": "inject"}]),
        ]
        scns = predicate_scenarios(planned)
        self.assertEqual(len(scns), 1)
        self.assertEqual(scns[0].id, "agentic-tool_principal_mismatch")
        # оба параметрических варианта присутствуют в меню сценария
        ats = [g.get("at") for g in scns[0].goal if g.get("type") == "tool_principal_mismatch"]
        self.assertEqual(set(ats), {"activate", "inject"})

    def test_missing_reset_provider_does_not_crash_the_run(self):
        # профиль без session_reset (напр. собранный из документов) → reset()
        # кидает UnsupportedFeature; агентный прогон должен продолжиться, как
        # reset_policy=none, а не падать
        from agentic_redteam.adapters.base import UnsupportedFeature

        class NoReset(FakeEvidenceSource):
            def reset(self):
                raise UnsupportedFeature("нет session_reset")

        agent = FakeLLM([json.dumps({"target": "memory_write",
                         "action": {"type": "message", "role": "attacker", "content": "x"}})])
        result = run_agentic(agent, FakeAdapter(roles={"attacker": "1001"}, responses=["a"]),
                             NoReset([Facts()]), surface={},
                             predicate_menu=[{"type": "memory_write", "scope": "cross_user"}],
                             roles=["attacker"], budget=1)
        self.assertEqual(result["verdict"], "not_proven")

    def test_seed_is_passed_through_to_run_agentic(self):
        captured = {}

        class Cap:
            def complete(self, prompt):
                captured["p"] = prompt
                return json.dumps({"target": "memory_write",
                                   "action": {"type": "message", "role": "attacker", "content": "x"}})

        run_agentic(Cap(), FakeAdapter(roles={"attacker": "1001"}, responses=["a"]),
                    FakeEvidenceSource([Facts()]), surface={},
                    predicate_menu=[{"type": "memory_write", "scope": "cross_user"}],
                    roles=["attacker"], budget=1, seed="СИД-ОТ-ГЕНЕРАТОРА")
        self.assertIn("СИД-ОТ-ГЕНЕРАТОРА", captured["p"])


if __name__ == "__main__":
    unittest.main()
