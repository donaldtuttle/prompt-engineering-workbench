# Supplied injector integrity — observed 2026-09-19

Classification: source-byte verification, not scientific validation. Confidence: ρ̂_conf_HIGH.

The archive member `reference/injectors/QOFT_XI_HEX_STANDALONE_v1.1_FINAL.txt` and the
separately supplied `39-28-QOFT_XI_HEX_STANDALONE_v1.1.txt` contain identical bytes.
The implementation copies those bytes to the path expected by the workbench loader:
`reference/injectors/QOFT_XI_HEX_STANDALONE_v1.1.txt`. Renaming did not alter content.

| Check | Expected by supplied manifest/specification | Actual supplied bytes |
| --- | --- | --- |
| Byte length | 80,140 | 82,644 |
| Line endings | LF only | 2,504 CRLF pairs |
| Full-file SHA-256 | `6ee2dc6f39bbc24aee92656aa74f71020caf7d4ca4c0897a3b14c0b245242db6` | `772bd882431107f5d1f622325a681402efbb05a76bb82df05abb7ffc6d7e0b27` |
| Scoped SHA-256 | `83b31740773a0ec0cc772104bf78fe4209a0161ef58b6ac8ecd20ebd4075a0c2` | `42c5ef3202123394cecc381fdf2498a149919cfe1f918df14957c12853fcfb43` |
| Scope | bytes [762, 80139), length 79,377 | Same offsets evaluated without normalization |

The embedded manifest in the old planning ZIP contains `PASTE_COMPLETE_GET-FILEHASH_RESULT_HERE`.
The separately supplied attachment 17 provides the expected complete full-file hash above;
that newer complete manifest is the selected runtime reference. Neither manifest is modified.

Disposition: **INVALID; FULL_INJECTOR blocked**. Original source bytes are retained. No
line-ending conversion, Unicode normalization, manifest repair, or automatic repinning occurs.
The app retains both calculated and expected values in the exported experiment record.

The safe corrective step is a separately authorized, provenance-recorded resolution of
the frozen content/manifest pair. Merely accepting the calculated hash would not establish
that these bytes are the intended frozen artifact.

## Independent software fixture

`DEMO_OFFLINE_FIXTURE.txt` is a newly authored 168-byte test artifact, not a derivative or
replacement injector. Its pinned full-file SHA-256 is
`adb50bebae4e3576c2c96c70866f4d1357888c35b2e13d76d2c88383870fc541`.
It enables successful baseline/treatment software checks while QOFT treatment stays blocked.

The original planning ZIP, source-level AGENTS.md, complete separately supplied PROJECT_BRIEF.md,
and injector/manifest copies are retained. `source-inventory.json` records the inspected
workbench archive, selected manifest, and supplied injector using the research skill's
non-executing corpus enumerator. Its scratch source paths are provenance, not runtime requirements.

