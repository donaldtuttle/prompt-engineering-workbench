# v0.2.0 review checklist

Use a fresh folder and temporary database. Never run review mutations against your history.

## Release and integrity

- [ ] Run uv sync --locked, pytest, Ruff lint, and Ruff format check.
- [ ] Verify 80,140 injector bytes and unchanged full/scoped pins.
- [ ] Verify the LF successor parses identically to the archived mixed-ending successor.
- [ ] Verify original inputs and v0.1.1 provenance remain unchanged.
- [ ] Confirm reviewer attestation is distinguished from builder access.
- [ ] Confirm tokenizer bytes match the pinned hash and mock control construction works offline.

## Persistence and execution

- [ ] Migrate a stopped copy of a v1 database; inspect the backup and compare raw old payloads.
- [ ] Confirm startup refuses schema 1, future schemas, and unversioned databases.
- [ ] Confirm old blocked records remain blocked; old exports remain v1.
- [ ] Create all delivery modes with two replicates; inspect initial/final messages and calls.
- [ ] Saturate admission and verify at most 16 jobs are admitted before preparation completes.
- [ ] Cancel during preparation, persistence, handshake, and queued execution; check interruption.
- [ ] Corrupt a QA copy after a run, replay the saved snapshot, and compare final hashes.
- [ ] Alter a stored prompt/hash pair inconsistently and confirm replay refusal.

## Provider and experimental boundary

- [ ] Inspect actual SDK mock-transport requests: exact messages/settings, no extra instructions,
      no tools/handoffs, no silent truncation, storage requested off, and no hidden retries.
- [ ] Confirm returned model string and missing usage handling, including incomplete SDK responses.
- [ ] Confirm no key or raw exception message enters exported records.
- [ ] Verify cloud is disabled without enablement/key; explicit model and consent are required.
- [ ] Run the optional browser smoke script and inspect desktop/mobile captures.
- [ ] Separately perform a small user-selected live OpenAI fixture smoke test, if desired.
      This step was NOT performed during the build.
- [ ] Before efficacy research, preregister probes/scoring/exclusions, validate tokenizer/control
      suitability, and add blinded evaluation. This release supplies no efficacy result.

D4 remains open before ablation matrices. Windows/macOS and other browsers remain unverified.
