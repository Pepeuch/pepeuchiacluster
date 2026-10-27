"""Offline standard-library tests for the pinned models.dev importer."""

from pathlib import Path
import io
import tempfile
import unittest

from import_models_dev import COPY_COLUMNS, emit_copy, make_row


SHA = "5e9fdbc3d88cb831627a93dc1362cc10773c176c"


class ImporterTests(unittest.TestCase):
    def test_model_metadata_and_copy_stream(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "models" / "openai" / "example.toml"
            source.parent.mkdir(parents=True)
            source.write_text(
                'schema = 2\nname = "Example, \\"alpha\\""\n'
                'family = "example"\nopen_weights = true\n'
                '[limit]\ncontext = 128000\n'
                '[capabilities]\ntools = { supported = true }\n'
                '[[weights]]\nurl = "https://example.invalid/weights"\n'
                '[[benchmarks]]\nname = "test"\nscore = 1.0\n',
                encoding="utf-8",
            )
            row = make_row(root, source, SHA)
            record = dict(zip(COPY_COLUMNS, row))
            self.assertEqual(record["source_path"], "models/openai/example.toml")
            self.assertEqual(record["model_id"], "openai/example")
            self.assertEqual(record["open_weights"], "true")
            self.assertEqual(record["tools_supported"], "true")
            self.assertEqual(record["context_tokens"], 128000)
            self.assertEqual(record["weights_count"], 1)
            self.assertEqual(record["benchmarks_count"], 1)
            out = io.StringIO()
            emit_copy([row], out)
            rendered = out.getvalue()
            self.assertIn("BEGIN;\n", rendered)
            self.assertIn('"Example, ""alpha"""', rendered)
            self.assertIn("\n\\.\nINSERT INTO", rendered)
            self.assertTrue(rendered.endswith("COMMIT;\n"))

    def test_missing_optional_values(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "models" / "org" / "bare.toml"
            source.parent.mkdir(parents=True)
            source.write_text('schema = 2\nname = "Bare"\n', encoding="utf-8")
            record = dict(zip(COPY_COLUMNS, make_row(root, source, SHA)))
            self.assertEqual(record["open_weights"], "")
            self.assertEqual(record["tools_supported"], "")
            self.assertEqual(record["context_tokens"], "")
            self.assertEqual(record["weights_count"], 0)

    def test_pinned_legacy_tool_call(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "models" / "openai" / "old.toml"
            source.parent.mkdir(parents=True)
            source.write_text(
                'name = "Old format"\ntool_call = true\n',
                encoding="utf-8",
            )
            record = dict(zip(COPY_COLUMNS, make_row(root, source, SHA)))
            self.assertEqual(record["tools_supported"], "true")
            source.write_text(
                'name = "Old format"\ntool_call = false\n',
                encoding="utf-8",
            )
            record = dict(zip(COPY_COLUMNS, make_row(root, source, SHA)))
            self.assertEqual(record["tools_supported"], "false")

    def test_conflicting_tool_capabilities_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "models" / "org" / "conflict.toml"
            source.parent.mkdir(parents=True)
            source.write_text(
                'tool_call = true\n[capabilities]\n'
                'tools = { supported = false }\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Conflicting models.dev"):
                make_row(root, source, SHA)


if __name__ == "__main__":
    unittest.main()
