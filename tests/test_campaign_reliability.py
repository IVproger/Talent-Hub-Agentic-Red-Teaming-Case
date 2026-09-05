import json
import tempfile
import unittest
from pathlib import Path

from tests.fakes import FakeAdapter, FakeEvidenceSource
from agentic_redteam.assertions.registry import required_kinds
from agentic_redteam.campaign.orchestrator import PlannedScenario, run_campaign, build_findings
from agentic_redteam.campaign.runner import RunnerDeps, ScenarioStep, run_scenario, RunResult, AttemptResult
from agentic_redteam.normalize.facts import Facts, ObservedToolCall
from agentic_redteam.storage.runs import RunStorage


def hit():
    return Facts(tool_calls=[ObservedToolCall('read', 'B', {}, 'audit')])


class ReliabilityTests(unittest.TestCase):
    def test_interrupt_preserves_previous_attempt_and_finalizes_status(self):
        class Interrupt(FakeEvidenceSource):
            def collect_facts(self, since):
                if self._collected == 1:
                    raise KeyboardInterrupt()
                return super().collect_facts(since)
        with tempfile.TemporaryDirectory() as root:
            scenario = PlannedScenario('s', 'bac', [], 'A', ['p'], [{'type': 'tool_principal_mismatch'}])
            deps = RunnerDeps(FakeAdapter({'attacker': 'A'}, ['ok']), Interrupt([hit(), hit()]))
            with self.assertRaises(KeyboardInterrupt):
                run_campaign([scenario], deps, RunStorage(root), 'r', trials=2)
            result = json.loads((Path(root)/'r'/'findings.json').read_text())
            directory = Path(root) / 'r'
            self.assertEqual(result['status'], 'interrupted')
            self.assertEqual(json.loads((directory/'status.json').read_text())['status'], 'interrupted')
            rows = [json.loads(line) for line in (directory/'transcript.jsonl').read_text().splitlines()]
            self.assertEqual([r['verdict'] for r in rows], ['proven', 'error'])
            self.assertTrue((directory / rows[0]['evidence_refs'][0]).exists())
            self.assertIn('Неполный', (directory/'report.md').read_text())
            self.assertEqual(result['attempts_scored'], 1)

    def test_completed_attempt_is_on_disk_before_next_send(self):
        with tempfile.TemporaryDirectory() as root:
            class CheckpointEvidence(FakeEvidenceSource):
                def reset(self):
                    if self.resets:
                        rows = (Path(root)/'r'/'transcript.jsonl').read_text().splitlines()
                        assert len(rows) == 1
                    super().reset()
            s = PlannedScenario('s', 'bac', [], 'A', ['p'], [{'type':'tool_principal_mismatch'}])
            deps = RunnerDeps(FakeAdapter({'attacker':'A'}, ['ok']), CheckpointEvidence([hit(),hit()]))
            result = run_campaign([s], deps, RunStorage(root), 'r', trials=2)
            self.assertEqual(result['attempts_scored'], 2)

    def test_optional_memory_does_not_block_state_proof(self):
        goal = [{'type':'memory_write','scope':'cross_user','optional':True}, {'type':'tool_principal_mismatch'}]
        self.assertEqual(required_kinds(goal), {'tool_calls'})
        result = run_scenario(['p'], goal, 'A', RunnerDeps(FakeAdapter({'attacker':'A'}, ['ok']), FakeEvidenceSource([hit()])))
        self.assertEqual(result.attempts[0].verdict, 'proven')

    def test_per_step_resets_each_step_and_none_never_resets(self):
        steps = [ScenarioStep('one','attacker',payload=True), ScenarioStep('two','attacker',message='continue')]
        for policy, resets in [('per_step',2),('per_scenario',1),('none',0)]:
            evidence = FakeEvidenceSource([hit(),hit()])
            run_scenario(['p'], [{'type':'tool_principal_mismatch','at':'two'}], 'A',
                         RunnerDeps(FakeAdapter({'attacker':'A'}, ['ok','ok']), evidence), steps=steps, reset_policy=policy)
            self.assertEqual(evidence.resets,resets)

    def test_asr_groups_scenarios_per_mode_and_counts_indirect(self):
        s = PlannedScenario('s','bac',[],'A',['p'],[])
        leak = PlannedScenario('leak','leak',[],'A',['p'],[])
        smoke = PlannedScenario('smoke','normal',[],'A',['p'],[], expect='pass')
        def result(*pairs):
            return RunResult('r','completed',[AttemptResult(i,'p','A',mode,v) for i,(mode,v) in enumerate(pairs)],0)
        findings = build_findings('r','p@1',[],[(s,result(('v','proven'),('v','not_proven'),('p','not_proven'))),
                    (leak,result(('v','indirect'),('p','error'))),(smoke,result(('v','proven')))])
        self.assertEqual(findings['scenarios_scored'],3)
        self.assertAlmostEqual(findings['asr_percent'],100/3)
        self.assertEqual(findings['asr_by_mode']['v']['asr_percent'],50)
        self.assertEqual(findings['attempts_scored'],4)
        self.assertTrue(findings['smoke'][0]['ok'])

    def test_first_proven_metric_ignores_smoke_success(self):
        attack = PlannedScenario('attack', 'bac', [], 'A', ['p'], [])
        smoke = PlannedScenario('smoke', 'normal', [], 'A', ['p'], [], expect='pass')
        attack_result = RunResult('r', 'completed', [
            AttemptResult(1, 'p', 'A', 'v', 'not_proven'),
        ], 0)
        smoke_result = RunResult('r', 'completed', [
            AttemptResult(1, 'p', 'A', 'v', 'proven'),
        ], 100)
        findings = build_findings('r', 'p@1', ['v'], [
            (attack, attack_result), (smoke, smoke_result),
        ])
        self.assertIsNone(findings['attempts_to_first_proven'])

    def test_optional_failure_does_not_replace_the_primary_attempt_signal(self):
        scenario = PlannedScenario(
            's', 'bac', [], 'A', ['p'],
            [
                {'type': 'memory_write', 'scope': 'cross_user', 'optional': True},
                {'type': 'tool_principal_mismatch'},
            ],
        )
        result = run_scenario(
            ['p'], scenario.goal, 'A',
            RunnerDeps(FakeAdapter({'attacker': 'A'}, ['ok']), FakeEvidenceSource([hit()])),
        )
        findings = build_findings('r', 'p@1', [], [(scenario, result)])
        self.assertIn('принципалу', findings['attempts'][0]['signal'])
        self.assertNotIn('память', findings['attempts'][0]['signal'])
