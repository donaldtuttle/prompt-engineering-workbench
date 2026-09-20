# Three-Lane Probe — offline protocol reconstruction

[Original Grok app](https://cactus-umbra-vivid-lunar.grok.me/)
· [Source inspection and remaining work](../../docs/THREE_LANE_RECONSTRUCTION.md)

**DEVELOP / partial reconstruction.** This Python module reproduces the observable
DEMO message assembly, prompt hashing, three delivery modes, tamper blocking, and
offline call records. It is not a recovered copy of the Grok server or its browser UI.

The module is separate from the v0.2.0 harness. It imports only the Python standard
library, sends nothing over the network, and writes JSON to stdout. It does not load
the private QOFT injector, change the main app, or open its database.

## Run from the repository root

Use Python 3.12+, matching the repository's runtime requirement.

```sh
python examples/three_lane_probe/probe.py
python examples/three_lane_probe/probe.py --delivery USER_PASTE
python examples/three_lane_probe/probe.py --delivery USER_PASTE_WITH_HANDSHAKE
python examples/three_lane_probe/probe.py --tamper-crlf
python examples/three_lane_probe/probe.py --task 'Keep this task exactly.'
```

Redirect stdout to a local file if you want to keep an export. Avoid committing
personal prompts or generated records.

Mock output is a synthetic acknowledgement, not an answer to the question. The
untampered run succeeds in three lanes. CRLF tampering changes the pinned 168-byte
fixture to 172 bytes and blocks both context lanes; baseline still runs. Handshake
mode records two fixture calls per successful lane.

## Verify

```sh
python -m unittest discover -s examples/three_lane_probe -p 'test_*.py' -v
```

Golden tests compare six complete prompt hashes and three handshake hash prefixes
against values observed in the original app. Other tests check isolation, artifact
integrity, exact task retention, call counts, and a changed-message refusal.

## Deliberate boundaries

- The output schema is `three-lane-reconstruction-v1`, not `workbench-experiment-v2`.
  Do not import it into the workbench as a harness export.
- The source client uses a fixed 40-token value for this exact DEMO fixture. This
  module records that provenance explicitly; it does not claim runtime tokenization
  or accept arbitrary injectors. General token matching belongs in the existing harness.
- The original server's exact handshake response was not recovered. This local mock
  returns `READY`; its final handshake-task hashes are not claimed to match Grok's.
- `fixture_boundary_hash` hashes bytes at a local function boundary. No network or
  model received them. A hash match proves no model effect or scientific mechanism.
- IDs and timestamps change between executions. Initial message hashes are deterministic.
- No Grok adapter, paid calls, SQLite history, browser interface, or UI fidelity claim
  is included. The UI reconstruction remains blocked pending mobile source capture
  and browser verification; see the inspection report.

Evaluation is null and resolution remains `INSUFFICIENT_EVIDENCE`.
