# Injector restoration — v0.1.1 — 2026-09-19

Disposition: **restored working artifact VALID; original CRLF source retained and rejected**.
Classification: engineering/source-byte verification, not scientific validation. (ρ̂_conf_HIGH)

## Evidence and authorization

The supplied standalone attachment and injector inside the July planning ZIP contain the
same 82,644-byte CRLF content. In-memory replacement of exactly 2,504 CRLF pairs with LF
produced bytes matching the separately supplied complete manifest's full-file and scoped
hashes. The user approved the complete v0.1.1 restoration release after review.

This release **reconstructs** the manifest-matching LF bytes from the preserved supplied
CRLF copy. It does not claim that a separate original LF file was retrieved or that Git,
an editor, or a specific transport step caused the drift. That mechanism remains unknown.
No QOFT canon/governance document is amended or empirically validated by this operation.

## Before and after

| Check | Preserved supplied CRLF source | Restored working LF artifact |
| --- | --- | --- |
| Byte length | 82,644 | 80,140 |
| Line endings | 2,504 CRLF pairs | 2,504 LF; no CR |
| Full-file SHA-256 | `772bd882431107f5d1f622325a681402efbb05a76bb82df05abb7ffc6d7e0b27` | `6ee2dc6f39bbc24aee92656aa74f71020caf7d4ca4c0897a3b14c0b245242db6` |
| Scoped SHA-256 at [762, 80139) | `42c5ef3202123394cecc381fdf2498a149919cfe1f918df14957c12853fcfb43` | `83b31740773a0ec0cc772104bf78fe4209a0161ef58b6ac8ecd20ebd4075a0c2` |
| Runtime disposition with successor manifest | INVALID / treatment BLOCKED | VALID / offline treatment permitted |

The restored hashes equal the **existing** manifest pins; neither pin nor scope changed.
No text, glyph, indentation, wording, or trailing-newline content was otherwise changed.

## Preserved artifacts and successor policy

- `reference/rejected/QOFT_XI_HEX_STANDALONE_v1.1.CRLF.txt`: supplied bytes, unchanged.
- `reference/original/QOFT_XI_HEX_STANDALONE_v1.1.manifest.original.json`: original complete
  manifest, unchanged; SHA-256 `6bfe67f552222f21b23f2c52e20bb0ed5a4a420872b8502e571ce37c2dbb538d`.
- `reference/original/Prompt-Engineering-Workbench-spec.zip`: planning ZIP, unchanged,
  including its older placeholder manifest. It is not the working runtime manifest.
- `reference/injectors/QOFT_XI_HEX_STANDALONE_v1.1.txt`: restored LF bytes.
- Working `.manifest.json`: explicit successor adding only `manifest_schema` and
  `required_line_endings`, with all original values preserved. Its byte hash is recorded
  in `restoration-provenance.json`, distinct from the unchanged injector-content pins.

## Reproducible operation

```sh
python scripts/restore_release_artifact.py
```

The script checks the exact reviewed input hash, source structure, original manifest length,
full hash, and scoped hash. It refuses a different existing destination or different provenance
record. Re-running against the unchanged release is idempotent. It is not imported by the app.
The runtime loader always reads raw bytes and rejects mismatches; it never repairs a file.

`.gitattributes` retains `reference/** -text` and adds `tests/fixtures/** -text`. Tests assert
that the restored source is VALID and the preserved CRLF bytes fail without modification.
Browser fault injection uses a temporary reference copy, not the actual release source.

## Policy semantics

The loader has no artifact-name rule. Any manifest can declare `required_line_endings`:
`LF` forbids CR; `CRLF` forbids bare CR or bare LF. No-newline files satisfy either rule.
Omitted policy supports legacy manifests; malformed policies/unknown schemas fail closed.
This is integrity against a supplied manifest, not authentication against malicious local edits.

Old experiment snapshots retain their original manifest and bytes. They are never upgraded
by comparing them to today's working copy. The restored artifact enables software trials;
mock completion is not an activation handshake or evidence of model effectiveness.

`docs/source-inventory.json` retains the v0.1.0 input inventory. The new
`docs/release-reference-inventory.json` records this release's reference files.
