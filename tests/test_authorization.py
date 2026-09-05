"""US-34: кампания не стартует без явной отметки, кто её разрешил."""
from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
from datetime import date, timedelta
from pathlib import Path

import yaml

from agentic_redteam.campaign.authorization import (
    Authorization,
    AuthorizationError,
    authorization_from_mapping,
)
from agentic_redteam.errors import PipelineConfigurationError
from tests.test_cli_execute import PROFILE, Adapter as _Adapter, Bundle, hit, run_cli


def mapping(**overrides) -> dict:
    block = {
        "authorized_by": "владелец стенда",
        "scope": "genai-invest-stand: учебный полигон",
        "until": date.today() + timedelta(days=30),
    }
    block.update(overrides)
    return {"authorization": block}


class AuthorizationTests(unittest.TestCase):
    def test_complete_block_is_accepted(self):
        auth = authorization_from_mapping(mapping())
        self.assertIsInstance(auth, Authorization)
        self.assertEqual(auth.authorized_by, "владелец стенда")

    def test_missing_block_refuses_the_run(self):
        with self.assertRaises(AuthorizationError) as caught:
            authorization_from_mapping({})
        self.assertIn("authorization", str(caught.exception))

    def test_each_field_is_required(self):
        for field in ("authorized_by", "scope", "until"):
            with self.subTest(field=field), self.assertRaises(AuthorizationError):
                authorization_from_mapping(mapping(**{field: ""}))

    def test_expired_window_refuses_the_run(self):
        """Просроченное разрешение — не разрешение."""
        with self.assertRaises(AuthorizationError) as caught:
            authorization_from_mapping(mapping(until=date.today() - timedelta(days=1)))
        self.assertIn("истек", str(caught.exception).lower())

    def test_window_ending_today_is_still_valid(self):
        self.assertTrue(authorization_from_mapping(mapping(until=date.today())))

    def test_unparsable_window_refuses_the_run(self):
        with self.assertRaises(AuthorizationError):
            authorization_from_mapping(mapping(until="когда-нибудь"))

    def test_iso_string_window_is_accepted(self):
        auth = authorization_from_mapping(mapping(until="2099-01-01"))
        self.assertEqual(auth.until, "2099-01-01")

    def test_record_is_what_lands_in_campaign_json(self):
        """Разрешение фиксируется в артефакте прогона (US-34, E7 §8)."""
        record = authorization_from_mapping(mapping(until="2099-01-01")).as_record()
        self.assertEqual(record, {
            "authorized_by": "владелец стенда",
            "scope": "genai-invest-stand: учебный полигон",
            "until": "2099-01-01",
        })


class GateInCliTests(unittest.TestCase):
    """Гейт стоит на пути исполнения и фиксируется в артефакте прогона."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def config(self, authorization: dict | None) -> str:
        block = {"llm": {}} | ({"authorization": authorization} if authorization else {})
        path = self.root / "config.yaml"
        path.write_text(yaml.safe_dump(block, allow_unicode=True), encoding="utf-8")
        return str(path)

    def test_run_without_authorization_is_refused_before_the_target_is_touched(self):
        code, out, adapter = run_cli(
            ["run", "--profile", PROFILE, "--scenario", "bac-tool-argument", "-o", str(self.root),
             "--config", self.config(None), "--json"],
            Bundle([hit()] * 20))
        self.assertEqual(code, 2)
        self.assertIn("authorization", json.loads(out)["error"])
        self.assertFalse(adapter.closed, "адаптер не должен был открываться")

    def test_expired_authorization_is_refused(self):
        expired = {"authorized_by": "кто-то", "scope": "стенд",
                   "until": (date.today() - timedelta(days=1)).isoformat()}
        code, out, _ = run_cli(
            ["run", "--profile", PROFILE, "--scenario", "bac-tool-argument", "-o", str(self.root),
             "--config", self.config(expired), "--json"],
            Bundle([hit()] * 20))
        self.assertEqual(code, 2)
        self.assertIn("истекло", json.loads(out)["error"])

    def test_authorization_is_recorded_in_the_campaign(self):
        allowed = {"authorized_by": "владелец стенда", "scope": "полигон",
                   "until": "2099-01-01"}
        code, out, _ = run_cli(
            ["run", "--profile", PROFILE, "--scenario", "bac-tool-argument", "-o", str(self.root),
             "--config", self.config(allowed), "--json"],
            Bundle([hit()] * 20))
        self.assertEqual(code, 0, out)
        run_dir = Path(json.loads(out)["run"]["run_dir"])
        campaign = json.loads((run_dir / "campaign.json").read_text(encoding="utf-8"))
        self.assertEqual(campaign["authorization"], allowed)

    def test_preview_does_not_need_authorization(self):
        """Предпросмотр цель не трогает, поэтому разрешение для него не требуется."""
        code, out, _ = run_cli(
            ["run", "--profile", PROFILE, "--scenario", "bac-tool-argument", "--dry-run",
             "--config", self.config(None), "--json"],
            Bundle([hit()] * 20))
        self.assertEqual(code, 0, out)


class SharedCoreGateTests(unittest.TestCase):
    """Гейт живёт в общем ядре запуска, а не в одном лишь CLI.

    UI зовёт `execute_campaign` напрямую (US-07 AC3: одно ядро на оба входа),
    поэтому проверка в `_execute_campaign` оставила бы демо без рамки.
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        from agentic_redteam.app_cli import load_profile
        self.profile = load_profile(PROFILE)

    def execute(self, **kwargs):
        from agentic_redteam.app_cli import execute_campaign
        with unittest.mock.patch("agentic_redteam.app_cli.EvidenceBundle") as bundle_cls, \
             unittest.mock.patch("agentic_redteam.app_cli.HttpChatAdapter") as adapter_cls:
            bundle_cls.from_profile.return_value = Bundle([hit()] * 20)
            adapter_cls.from_profile.return_value = _Adapter(
                {"attacker": "1001", "victim": "1002"}, ["ok"] * 40)
            return execute_campaign(self.profile, [], [], 1, str(self.root),
                                    "run-1", **kwargs)

    def test_execute_campaign_refuses_without_authorization(self):
        with self.assertRaises(AuthorizationError):
            self.execute()

    def test_execute_campaign_accepts_a_recorded_authorization(self):
        """С разрешением гейт пропускает — дальше уже обычные проверки."""
        allowed = {"authorized_by": "владелец", "scope": "полигон", "until": "2099-01-01"}
        with self.assertRaises(PipelineConfigurationError):
            # Пустой список сценариев валится на гейте покрытия, а не на рамке.
            self.execute(authorization=allowed)


if __name__ == "__main__":
    unittest.main()
