import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("recover", Path(__file__).with_name("recover-openapi.py"))
recover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover)
OPENAPI = b'swagger: "2.0"\ninfo:\n  title: Existing API\n  version: "1"\npaths:\n  /old: {}\n'


class RecoveryTests(unittest.TestCase):
    def test_existing_directory_multiple_configs_and_idempotence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "target") as directory:
            root = Path(directory)
            output = root / "deploy" / "recovered-openapi"
            output.mkdir(parents=True)
            sentinel = output.parent / "env.yaml"
            sentinel.write_text("preserve me")
            sources = []
            for name in ("echo-1.yml", "token-fpe-cadp-gcp-nbr-.yml"):
                source = root / name
                source.write_text(json.dumps({"name": name, "openapiDocuments": [{"document": {
                    "path": "../../outside.yaml", "contents": base64.b64encode(OPENAPI).decode()}}]}))
                sources.append(str(source))
            args = [*sources, "--output-dir", str(output)]
            self.assertEqual(recover.main(args), 0)
            self.assertEqual(recover.main(args), 0)
            self.assertEqual(sentinel.read_text(), "preserve me")
            self.assertEqual(len(list(output.glob("*.yaml"))), 2)
            self.assertEqual((output / "echo-1--1.yaml").read_bytes(), OPENAPI)
            self.assertFalse((root / "outside.yaml").exists())

    def test_plain_openapi_yaml(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "target") as directory:
            source = Path(directory) / "already.yml"
            source.write_bytes(OPENAPI)
            self.assertEqual(recover.documents(source)[1][0][1], OPENAPI)

    def test_conflict_does_not_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "target") as directory:
            path = Path(directory) / "existing.yaml"
            path.write_bytes(b"existing")
            with self.assertRaises(ValueError):
                recover.write_preserving(path, OPENAPI)
            self.assertEqual(path.read_bytes(), b"existing")

    def test_bad_base64(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "target") as directory:
            source = Path(directory) / "bad.yml"
            source.write_text(json.dumps({"openapiDocuments": [{"document": {"contents": "!!!"}}]}))
            with self.assertRaises(ValueError):
                recover.documents(source)


if __name__ == "__main__":
    unittest.main()

