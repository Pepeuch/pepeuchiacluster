"""Offline tests for the SurrealDB models.dev POC import generator."""

import io
import json
from pathlib import Path
import tempfile
import unittest

from import_models_dev import make_row
from import_models_dev_surreal import emit_surql, make_record, record_id


SHA = "5e9fdbc3d88cb831627a93dc1362cc10773c176c"


class SurrealImporterTests(unittest.TestCase):
    def _fixture(self, content: str) -> dict:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            path = root / "models" / "org" / "sample.toml"
            path.parent.mkdir(parents=True)
            path.write_text(content, encoding="utf-8")
            return make_record(make_row(root, path, SHA))

    def test_metadata_types_and_surql(self) -> None:
        record = self._fixture(
            'name = "A {special} \\"quoted\\" model"\n'
            'family = "example"\nopen_weights = true\n'
            '[limit]\ncontext = 128000\n'
            '[capabilities]\ntools = { supported = false }\n'
            '[[weights]]\nurl = "https://example.invalid/weights"\n'
            '[[benchmarks]]\nname = "benchmark"\nscore = 1.0\n'
        )
        self.assertTrue(record["open_weights"])
        self.assertFalse(record["tools_supported"])
        self.assertEqual(record["context_tokens"], 128000)
        self.assertEqual(record["weights_count"], 1)
        self.assertEqual(record["benchmarks_count"], 1)
        self.assertEqual(record["source_commit"], SHA)
        out = io.StringIO()
        emit_surql([record], out)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "OPTION IMPORT;")
        self.assertEqual(len([s for s in lines if s.startswith("UPSERT ")]), 1)
        statement = lines[-1]
        self.assertTrue(statement.startswith("UPSERT external_models:m_"))
        self.assertTrue(statement.endswith(" RETURN NONE;"))
        parsed = json.loads(statement.split(" CONTENT ", 1)[1].rsplit(" RETURN NONE;", 1)[0])
        self.assertEqual(parsed, record)

    def test_missing_values_and_zero_are_distinct(self) -> None:
        missing = self._fixture('name = "Bare"\n')
        zero = self._fixture('name = "Bare"\n[limit]\ncontext = 0\n')
        self.assertIsNone(missing["context_tokens"])
        self.assertEqual(zero["context_tokens"], 0)
        self.assertIsNone(missing["open_weights"])
        self.assertIsNone(missing["tools_supported"])

    def test_stable_snapshot_id_and_upsert(self) -> None:
        record = self._fixture('name = "Bare"\n')
        first_id = record_id(record)
        self.assertEqual(first_id, record_id(record.copy()))
        record["display_name"] = "Changed display name"
        self.assertEqual(first_id, record_id(record))
        record["source_commit"] = "0" * 40
        self.assertNotEqual(first_id, record_id(record))


if __name__ == "__main__":
    unittest.main()
