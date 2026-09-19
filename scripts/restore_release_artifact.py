"""Explicit, pinned release-time restoration. Never imported by the application.

The original CRLF source and original manifest are immutable inputs. Only CRLF
pairs are converted; exact existing pins must match before a new file is written.
This is not a runtime normalizer or an instruction to repin a failed artifact.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_SHA256 = "772bd882431107f5d1f622325a681402efbb05a76bb82df05abb7ffc6d7e0b27"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def restore_bytes(source: bytes, manifest: dict) -> bytes:
    if len(source) != 82644 or sha256(source) != SOURCE_SHA256:
        raise ValueError("Not the reviewed CRLF source; restoration refused")
    if source.count(b"\r\n") != 2504 or source.count(b"\r") != 2504:
        raise ValueError("Unexpected line-ending structure; restoration refused")
    restored = source.replace(b"\r\n", b"\n")
    if len(restored) != manifest["expected_byte_length"]:
        raise ValueError("Restored byte length does not match the original manifest")
    if sha256(restored) != manifest["full_file_sha256"]:
        raise ValueError("Restored full hash does not match the original manifest")
    scope = manifest["scoped_verification"]
    start, end = scope["start_offset_zero_based"], scope["end_offset_exclusive"]
    if scope["algorithm"] != "sha256" or end - start != scope["length_bytes"]:
        raise ValueError("Invalid original scope")
    if sha256(restored[start:end]) != scope["expected_sha256"]:
        raise ValueError("Restored scope does not match the original manifest")
    return restored


def main() -> None:
    source_path = ROOT / "reference/rejected/QOFT_XI_HEX_STANDALONE_v1.1.CRLF.txt"
    manifest_path = ROOT / "reference/original/QOFT_XI_HEX_STANDALONE_v1.1.manifest.original.json"
    target = ROOT / "reference/injectors/QOFT_XI_HEX_STANDALONE_v1.1.txt"
    successor_path = target.with_suffix(".manifest.json")
    source, original_manifest = source_path.read_bytes(), manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    restored = restore_bytes(source, manifest)
    successor = json.loads(successor_path.read_bytes())
    expected_successor = {
        **manifest,
        "manifest_schema": "workbench-artifact-manifest-v2",
        "required_line_endings": "LF",
    }
    if successor != expected_successor:
        raise ValueError("Successor manifest changed more than the declared policy metadata")
    if target.exists():
        if target.read_bytes() != restored:
            raise ValueError("Destination exists with different bytes; it was not overwritten")
    else:
        with target.open("xb") as stream:
            stream.write(restored)
    report = {
        "release": "0.2.0",
        "restoration_date": "2026-09-19",
        "authority": "User approved complete v0.2.0 release; v0.1.1 restoration retained",
        "method": "Explicit release-time CRLF-to-LF byte reconstruction; never runtime loading",
        "source": str(source_path.relative_to(ROOT)),
        "source_bytes": len(source),
        "source_sha256": sha256(source),
        "crlf_pairs_replaced": 2504,
        "target": str(target.relative_to(ROOT)),
        "target_bytes": len(restored),
        "target_sha256": sha256(restored),
        "scoped_sha256": sha256(restored[762:80139]),
        "original_manifest_sha256": sha256(original_manifest),
        "successor_manifest_sha256": sha256(successor_path.read_bytes()),
        "previous_successor_manifest_sha256": (
            "9495821f63292e947d884f7754c3119fe9a90247ee73e2a41623d2b47030596d"
        ),
        "manifest_change": (
            "Successor CRLF pairs deliberately converted to LF; JSON values unchanged"
        ),
        "reviewer_attestation": {
            "date": "2026-09-19",
            "source": "User-supplied peer review of v0.1.0 and v0.1.1",
            "claim": (
                "Reviewer compared restored bytes with canonical project LF copy: byte-identical"
            ),
            "independently_reperformed_by_this_build": False,
        },
        "injector_hash_pins_changed": False,
        "original_inputs_preserved": True,
        "independent_original_LF_copy_accessed": False,
        "transport_mechanism": "UNKNOWN; Git/editor conversion not established",
    }
    report_path = ROOT / "docs/restoration-provenance.json"
    encoded = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
    if report_path.exists() and report_path.read_bytes() != encoded:
        raise ValueError("Existing provenance differs; it was not overwritten")
    if not report_path.exists():
        with report_path.open("xb") as stream:
            stream.write(encoded)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
