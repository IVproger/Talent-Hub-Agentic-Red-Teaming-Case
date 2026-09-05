import json
import tempfile
import unittest
from pathlib import Path

import yaml

from agentic_redteam.profile.ingest import build_draft


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


if __name__ == "__main__":
    unittest.main()
