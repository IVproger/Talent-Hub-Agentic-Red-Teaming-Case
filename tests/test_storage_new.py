import json
import tempfile
import unittest
from pathlib import Path

from agentic_redteam.storage.runs import RunStorage, StorageError


class StorageNewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.storage = RunStorage(self.tmp)

    def test_write_campaign(self):
        run = self.storage.create("run-1")
        self.storage.write_campaign(run, {"profile": "p@1", "trials": 5})
        data = json.loads((Path(run) / "campaign.json").read_text())
        self.assertEqual(data["profile"], "p@1")

    def test_append_transcript(self):
        run = self.storage.create("run-2")
        self.storage.append_transcript(run, {"payload": "a"})
        self.storage.append_transcript(run, {"payload": "b"})
        lines = (Path(run) / "transcript.jsonl").read_text().splitlines()
        self.assertEqual([json.loads(x)["payload"] for x in lines], ["a", "b"])

    def test_immutable_create(self):
        self.storage.create("run-3")
        with self.assertRaises(StorageError):
            self.storage.create("run-3")


if __name__ == "__main__":
    unittest.main()
