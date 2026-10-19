#!/usr/bin/env python3
"""Recover separate OpenAPI documents from config exports; never merge configs."""
import argparse
import base64
import binascii
import json
from pathlib import Path
import re
import sys


def looks_like_openapi(text):
    return bool(re.search(r"^(?:swagger|openapi)\s*:", text, re.MULTILINE))


def documents(source):
    text = source.read_text(encoding="utf-8-sig")
    try:
        config = json.loads(text)
    except json.JSONDecodeError:
        if looks_like_openapi(text):
            return "already OpenAPI", [(source.name, text.encode("utf-8"))]
        try:
            import yaml
        except ImportError as error:
            raise ValueError("not JSON or recognizable OpenAPI YAML; if this is a YAML "
                             "config export, install PyYAML with python3 -m pip install --user PyYAML") from error
        config = yaml.safe_load(text)
    if not isinstance(config, dict):
        raise ValueError("expected a config object or OpenAPI document")
    if "swagger" in config or "openapi" in config:
        return "already OpenAPI", [(source.name, text.encode("utf-8"))]
    exports = config.get("openapiDocuments")
    if not isinstance(exports, list) or not exports:
        raise ValueError("no openapiDocuments found; this may be notes rather than a FULL config export")
    recovered = []
    for number, entry in enumerate(exports, 1):
        try:
            doc = entry["document"]
            # YAML block scalars may wrap base64 across lines.
            contents = base64.b64decode("".join(doc["contents"].split()), validate=True)
            decoded = contents.decode("utf-8-sig")
        except (KeyError, TypeError, AttributeError, UnicodeError, binascii.Error) as error:
            raise ValueError(f"document {number} has missing or invalid base64 contents") from error
        try:
            parsed = json.loads(decoded)
            valid = isinstance(parsed, dict) and ("swagger" in parsed or "openapi" in parsed)
        except json.JSONDecodeError:
            valid = looks_like_openapi(decoded)
        if not valid:
            raise ValueError(f"document {number} does not look like OpenAPI")
        recovered.append((doc.get("path", f"document-{number}"), contents))
    return config.get("name", "config export"), recovered


def write_preserving(path, contents):
    try:
        with path.open("xb") as output:
            output.write(contents)
        return "created"
    except FileExistsError:
        if path.read_bytes() == contents:
            return "unchanged"
        raise ValueError(f"refusing to overwrite different existing content: {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="input files; default: ./*.yml")
    parser.add_argument("--output-dir", default="deploy/recovered-openapi")
    args = parser.parse_args(argv)
    sources = [Path(name) for name in args.files] if args.files else sorted(Path.cwd().glob("*.yml"))
    if not sources:
        parser.error("no .yml files found in the current directory")
    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    failures = 0
    for source in sources:
        try:
            identity, recovered = documents(source)
            stem = re.sub(r"[^A-Za-z0-9_.-]", "_", source.stem)
            print(f"\n{source.name}: {identity}")
            for number, (original_path, contents) in enumerate(recovered, 1):
                # Never use a path from an export as a filesystem destination.
                output = destination / f"{stem}--{number}.yaml"
                action = write_preserving(output, contents)
                print(f"  {action}: {output} (original document: {original_path})")
        except (OSError, ValueError) as error:
            failures += 1
            print(f"ERROR {source}: {error}", file=sys.stderr)
    print("\nConfigs remain separate. Select the active config before making a working copy.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
