"""Byte-preserving loads. Integrity errors are records, never silent repairs."""

import base64
import hashlib
import json
import re
from pathlib import Path

from .models import ArtifactIdentity, ArtifactSnapshot, now

MAX_ARTIFACT_BYTES = 2_000_000
SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _safe(self, name: str) -> Path:
        if not name or "/" in name or "\\" in name or Path(name).name != name:
            raise ValueError("Artifact must be a filename inside the approved reference directory")
        path = self.root / name
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError(
                "Artifact symlinks and paths outside the reference directory are rejected"
            )
        return path

    def _read(self, path: Path) -> bytes:
        with path.open("rb") as stream:
            data = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ValueError("Artifact exceeds the 2 MB limit")
        return data

    def ids(self) -> list[str]:
        return sorted(
            p.name.removesuffix(".manifest.json")
            for p in self.root.glob("*.manifest.json")
            if not p.is_symlink()
        )

    def load(self, artifact_id: str) -> ArtifactSnapshot:
        manifest_path = self._safe(artifact_id + ".manifest.json")
        manifest_bytes = self._read(manifest_path)
        errors: list[str] = []
        data = b""
        manifest = {}
        filename = artifact_id + ".txt"
        try:
            manifest = json.loads(manifest_bytes)
            if not isinstance(manifest, dict):
                raise ValueError("Manifest must be a JSON object")
            filename = manifest["filename"]
            data = self._read(self._safe(filename))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            errors.append(f"Cannot load declared artifact: {type(exc).__name__}")
            if not isinstance(manifest, dict):
                manifest = {}

        expected = manifest.get("full_file_sha256")
        size = manifest.get("expected_byte_length")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            errors.append("Manifest full_file_sha256 is missing or not a complete SHA-256")
            expected = None
        elif digest(data) != expected.lower():
            errors.append("Full-file SHA-256 mismatch")
        if type(size) is not int or size < 0:
            errors.append("Manifest expected_byte_length is invalid")
            size = None
        elif len(data) != size:
            errors.append(f"Byte length mismatch: expected {size}; received {len(data)}")

        encoding = None
        try:
            data.decode("utf-8", errors="strict")
            encoding = "UTF-8"
        except UnicodeDecodeError:
            errors.append("Artifact is not valid UTF-8")
        if data.startswith(b"\xef\xbb\xbf"):
            errors.append("UTF-8 BOM is unsupported; bytes were not modified")
        schema = manifest.get("manifest_schema", "workbench-artifact-manifest-v1")
        if schema not in ("workbench-artifact-manifest-v1", "workbench-artifact-manifest-v2"):
            errors.append("Unsupported artifact manifest schema")
        if "required_line_endings" in manifest:
            policy = manifest["required_line_endings"]
            if policy not in ("LF", "CRLF"):
                errors.append("Invalid required_line_endings policy: expected LF or CRLF")
            elif policy == "LF" and b"\r" in data:
                errors.append("Line-ending policy mismatch: LF required; supplied bytes contain CR")
            elif policy == "CRLF":
                # Inspect only; no conversion or normalization of input occurs.
                pairs = data.count(b"\r\n")
                if data.count(b"\r") != pairs or data.count(b"\n") != pairs:
                    errors.append("Line-ending policy mismatch: CRLF required; bare CR/LF found")

        scoped_hash = expected_scoped = None
        scope = manifest.get("scoped_verification")
        if scope is not None:
            try:
                if not isinstance(scope, dict) or scope.get("algorithm") != "sha256":
                    raise ValueError("Unsupported scope algorithm")
                start, length, end = (
                    scope[k]
                    for k in ("start_offset_zero_based", "length_bytes", "end_offset_exclusive")
                )
                if any(type(n) is not int for n in (start, length, end)):
                    raise ValueError("Offsets must be integers")
                if not 0 <= start < end <= len(data) or start + length != end:
                    raise ValueError("Offsets inconsistent or outside file")
                scoped_hash = digest(data[start:end])
                expected_scoped = scope["expected_sha256"]
                if not isinstance(expected_scoped, str) or not SHA256.fullmatch(expected_scoped):
                    expected_scoped = None
                    raise ValueError("Expected scope hash invalid")
                if scoped_hash != expected_scoped.lower():
                    errors.append("Scoped SHA-256 mismatch at the declared byte offsets")
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"Invalid scoped verification: {exc}")

        crlf = data.count(b"\r\n")
        endings = "CRLF" if crlf and data.count(b"\n") == crlf else "LF"
        if data.count(b"\r") != crlf or (crlf and data.count(b"\n") != crlf):
            endings = "mixed/CR"
        if b"\r" not in data and b"\n" not in data:
            endings = "none"
        identity = ArtifactIdentity(
            artifact_id=artifact_id,
            source_path=f"reference/injectors/{filename}",
            byte_length=len(data),
            sha256=digest(data),
            encoding=encoding,
            line_endings=endings,
            loaded_at=now(),
            status="INVALID" if errors else "VALID",
            expected_byte_length=size,
            expected_sha256=expected,
            scoped_sha256=scoped_hash,
            expected_scoped_sha256=expected_scoped,
            manifest_sha256=digest(manifest_bytes),
            diagnostics=errors,
        )
        return ArtifactSnapshot(
            identity=identity,
            bytes_base64=base64.b64encode(data).decode("ascii"),
            manifest_bytes_base64=base64.b64encode(manifest_bytes).decode("ascii"),
        )
