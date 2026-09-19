# v0.2.0 integrity and provenance record

Date: 2026-09-19. Scope: workbench release artifacts, not a complete QOFT canon audit.
Classification: governance/integrity record. The harness does not implement canonical operators.

## Injector unchanged from accepted v0.1.1

| Property | Preserved CRLF input | Restored LF working input |
| --- | --- | --- |
| Bytes | 82,644 | 80,140 |
| CRLF pairs | 2,504 | 0 |
| SHA-256 | 772bd882431107f5d1f622325a681402efbb05a76bb82df05abb7ffc6d7e0b27 | 6ee2dc6f39bbc24aee92656aa74f71020caf7d4ca4c0897a3b14c0b245242db6 |
| Runtime status | INVALID | VALID |

The restored scoped hash at [762, 80139) is
83b31740773a0ec0cc772104bf78fe4209a0161ef58b6ac8ecd20ebd4075a0c2.
Both injector pins are the original manifest values. No new injector content or pin was introduced.
The runtime loader never normalizes either source text or manifests.

## D7 successor manifest cleanup

The v0.1.1 successor had 13 CRLF endings and four standalone LF endings.
It is preserved byte-for-byte under
reference/original/QOFT_XI_HEX_STANDALONE_v1.1.manifest.v0.1.1.json.

The working successor now has LF-only endings. This explicit release-time transform replaces
only CRLF pairs. Parsed JSON is unchanged, including every injector/scoped pin.

| Manifest | SHA-256 |
| --- | --- |
| Original supplied manifest | 6bfe67f552222f21b23f2c52e20bb0ed5a4a420872b8502e571ce37c2dbb538d |
| v0.1.1 successor | 9495821f63292e947d884f7754c3119fe9a90247ee73e2a41623d2b47030596d |
| v0.2.0 LF successor | 918266f4849ad9b64fbd4bc8db41c78bc5d934609a11c2e6ab16571121700da1 |

The successor differs semantically from the original only by manifest_schema and
required_line_endings. scripts/restore_release_artifact.py asserts that equality and the
original injector pins before writing, refuses differing destinations/provenance, and is
not imported or invoked by the application. Tests import its pure restoration function.

## Independent confirmation is attributed

The user-supplied peer review dated 2026-09-19 reports an independent comparison with the
canonical project LF copy and byte identity with the reconstruction.
This is recorded as reviewer_attestation in restoration-provenance.json.

The build itself did not independently retrieve that separate LF copy. Consequently
independent_original_LF_copy_accessed remains false, and the original v0.1.1 provenance
record is preserved under docs/history/. This separates the build's access history from
later reviewer evidence. The precise Git/editor transport culprit remains unknown.

## Offline control dependency

The release additionally pins bundled o200k_base tokenizer data to SHA-256
446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d.
See reference/tokenizers/README.md for source, size, and license. It is a control-construction
dependency, not a QOFT authority source.

release-reference-inventory.json enumerates this release's reference bytes.
source-inventory.json is retained as the historical supplied-source inventory.
Byte hashes establish identity/integrity; they do not establish authorship, activation,
semantic neutrality, scientific truth, or model effectiveness.
