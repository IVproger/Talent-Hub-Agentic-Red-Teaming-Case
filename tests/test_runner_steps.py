"""The runner executes a scenario chain as one attempt (role switching included)."""
from __future__ import annotations

import unittest

from agentic_redteam.campaign.runner import RunnerDeps, ScenarioStep, run_scenario
from agentic_redteam.normalize.facts import Facts, ObservedToolCall
from tests.fakes import FakeEvidenceSource


class RecordingSession:
    def __init__(self, log, role, session_id, reply):
        self._log, self.role, self.session_id, self._reply = log, role, session_id, reply

    def send(self, message: str) -> str:
        self._log.append(("send", self.role, self.session_id, message))
        return self._reply

    def commit_memory(self) -> list[dict]:
        self._log.append(("commit", self.role, self.session_id, None))
        return []


class RecordingAdapter:
    def __init__(self, reply="ответ"):
        self.log: list[tuple] = []
        self._reply = reply

    def open_session(self, role, session_id, mode):
        self.log.append(("open", role, session_id, mode))
        return RecordingSession(self.log, role, session_id, self._reply)


CHAIN = [
    ScenarioStep("inject", "attacker", payload=True),
    ScenarioStep("finalize", "attacker", commit_memory=True),
    ScenarioStep("activate", "victim", message="мой портфель?"),
]


def facts_with(principal):
    return Facts(tool_calls=[ObservedToolCall("get_portfolio", principal, {}, "raw")])


class ChainExecutionTests(unittest.TestCase):
    def _run(self, goal, adapter=None, facts=None, steps=CHAIN):
        adapter = adapter or RecordingAdapter()
        evidence = FakeEvidenceSource([facts or facts_with("1003")])
        result = run_scenario(["ОТРАВА"], goal, actor="1002",
                              deps=RunnerDeps(adapter, evidence),
                              steps=steps, run_id="r1")
        return adapter, evidence, result

    def test_chain_is_one_attempt_with_all_steps(self):
        adapter, evidence, result = self._run([{"type": "tool_principal_mismatch", "at": "activate"}])
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.attempts[0].verdict, "proven")
        self.assertEqual([row[0] for row in adapter.log],
                         ["open", "send", "commit", "open", "send"])
        self.assertEqual(evidence.resets, 1)

    def test_actor_keeps_one_session_across_its_steps(self):
        adapter, _, _ = self._run([{"type": "tool_principal_mismatch", "at": "activate"}])
        opened = [(row[1], row[2]) for row in adapter.log if row[0] == "open"]
        self.assertEqual([role for role, _ in opened], ["attacker", "victim"])
        self.assertNotEqual(opened[0][1], opened[1][1])
        inject, commit = [row for row in adapter.log if row[0] in ("send", "commit")][:2]
        self.assertEqual(inject[2], commit[2])   # finalize hits the injecting session

    def test_payload_fills_the_marked_step_others_keep_their_message(self):
        adapter, _, _ = self._run([{"type": "tool_principal_mismatch", "at": "activate"}])
        sent = [row[3] for row in adapter.log if row[0] == "send"]
        self.assertEqual(sent, ["ОТРАВА", "мой портфель?"])

    def test_response_contains_binds_to_the_named_step(self):
        adapter = RecordingAdapter(reply="итог: КАНАРЕЙКА")
        _, _, result = self._run(
            [{"type": "response_contains", "at": "activate", "value": "КАНАРЕЙКА"}],
            adapter=adapter, facts=Facts())
        self.assertEqual(result.attempts[0].verdict, "indirect")

    def test_flat_payload_list_still_runs_one_attempt_per_payload(self):
        adapter = RecordingAdapter()
        evidence = FakeEvidenceSource([facts_with("1003"), facts_with("1001")])
        result = run_scenario(["a", "b"], [{"type": "tool_principal_mismatch"}],
                              actor="1001", deps=RunnerDeps(adapter, evidence), run_id="r2")
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual([row[1] for row in adapter.log if row[0] == "open"],
                         ["attacker", "attacker"])
        self.assertEqual([row[3] for row in adapter.log if row[0] == "send"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
