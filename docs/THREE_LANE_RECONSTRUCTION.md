# Three-Lane Probe: reverse-engineering record

Date: 2026-09-20. Status: **DEVELOP — partial reconstruction**.

Source: <https://cactus-umbra-vivid-lunar.grok.me/>.
Repository inspected at `296bca71dc231b8343800a67f15310f6560bd8d0` (v0.2.0).

## What is available

The public app is titled **Three-Lane Probe**, with subtitle **Workbench protocol
viewport**. Its page explicitly says it is not protocol-conformant with the local
Python harness. The source page, compiled client logic, and CSS were retrieved and
inspected; the desktop interface and mock interactions were exercised in a browser.
These are direct source observations, not evidence about model effectiveness.
(ρ̂_conf_HIGH)

The accompanying [offline module](../examples/three_lane_probe/README.md) reconstructs
the observable message assembly and integrity demonstration. It uses a separate
export schema and local fixture implementation. It does not replace or amend the
workbench controller, providers, frozen artifacts, database, or experiment schema.

This is an implementation inspection, not a complete QOFT canon audit. No D-Π-01
corpus validation or physical/consciousness experiment was performed. The baseline
for comparison is the original app's visible mock behavior and initial prompt hashes.

## Recovered contract

| Surface | Observed behavior | Reconstruction status |
| --- | --- | --- |
| Plain / Clear | `BASELINE`, no instruction context | Implemented |
| Packed / Front | `FULL_INJECTOR`, exact DEMO context | Implemented |
| Matched length / Fog | `NEUTRAL_LENGTH_CONTROL`, `" stone"` repeated 40 times | Fixed DEMO construction implemented |
| Hidden note | `SYSTEM_SLOT`, context in system role | Implemented |
| Pasted first | `USER_PASTE`, context in a separate user message | Implemented |
| Handshake then question | Preparation call before task; task withheld initially | Implemented with explicitly local READY fixture |
| Tamper checkbox | CRLF DEMO fails integrity; context lanes block | Implemented |
| Prompt fingerprint | First 24 hexadecimal digits displayed as 2 × 12 color cells | Algorithm recovered; UI not ported |
| Event rail | Phase-call hashes and blocked lanes | Local JSON call records only |
| Live Grok | Client requests `grok-4.5`, consent required | Server not recovered; no paid call made |
| Export | Browser constructs JSON Blob and downloads it | Local JSON export implemented; source download capture timed out |

Source-defined prompt serialization is compact JSON of ordered `{role, content}`
objects, UTF-8 encoded and SHA-256 hashed. Default and pasted-context golden hashes
were independently reproduced in Python. (ρ̂_conf_HIGH)

The canonical QOFT operator realization is not tested here. This app uses a public
software fixture and retains `INSUFFICIENT_EVIDENCE`; matching hashes establish
message-construction agreement only. (ρ̂_conf_HIGH)

## Original app checks performed

- Default Mock/System-slot: three recorded lanes, three displayed hash matches.
- Mock/Handshake: three recorded lanes, six displayed hash matches.
- Mock/Handshake with CRLF tamper: one recorded lane, two blocked lanes, two displayed
  hash matches; the context lanes had no displayed provider phase calls.
- Pasted-first preview: captured three complete initial prompt hashes.
- Desktop screenshot captured and inspected; source layout is three panels with
  task/settings on the left, comparison in the center, and provenance on the right.

The hash-match counters above are observations of the source UI, not an independent
audit of its server transport. (ρ̂_conf_HIGH)

## Important reconstruction boundaries

1. **Hidden server functions.** The route bundle delegates execution and provider
   availability to server functions. Server source, provider credentials, exact
   request construction, retries, and timeout enforcement were not recovered.
   UI statements about them are not independently verified server guarantees.
2. **Fixed client token count.** In the inspected `Pt` function, preview `tokenCount`
   begins at 40 and becomes null on diagnostics or a word-count mismatch. The pinned
   hash constrains this to the exact fixture. That client path is not a general
   runtime tokenizer, regardless of the nearby tokenizer description. This does not
   establish what the hidden server uses. (ρ̂_conf_HIGH)
3. **Client session budget.** The visible two-run Grok counter is kept in
   `sessionStorage`. This cannot establish a server-enforced spending limit; hidden
   server controls remain unknown. (ρ̂_conf_HIGH)
4. **Export-schema collision.** The original client labels its camelCase viewport
   record `workbench-experiment-v2` despite disclaiming harness conformance. The
   reconstruction uses a distinct schema name to avoid implying compatibility.
5. **Handshake output.** The original UI showed final task hashes, but its complete
   handshake replies were not captured. Our `READY` reply is an explicit local
   fixture policy; exact final handshake-task equivalence remains unverified.
6. **Control interpretation.** Repeated `stone` text is a length-control construction,
   not demonstrated semantic neutrality. Mock responses cannot establish a causal
   injector effect. (ρ̂_conf_HIGH)

## Source provenance

The retrieved public assets were inspected as data, not incorporated as executable
dependencies. No private injector text is copied into the reconstruction.

| Retrieved resource | SHA-256 of captured bytes |
| --- | --- |
| `/` HTML | `0e62675a1f59a1ea9b86e3475be65ac01adfe61ebd02d08494a9d4487a799e5e` |
| `/assets/routes-un1ROiTs.js` | `11aaa7f1bfc35cbc6cd02ed52e10ee5097b2a54c630ba9c6b34c0b3e6ff6a9a7` |
| `/assets/styles-C0NMsbOf.css` | `7c5f9fcdfc3620f409cab7df2a0910389769fd64610be3860dce29770eeb2e06` |

These are capture hashes, not upstream release signatures. Remote content can change.

## Verification and remaining work

The offline module has 11 standard-library unit tests. They cover source golden
vectors, all three delivery modes, tamper blocking, call counts, exact Unicode task
retention, input validation, hash mismatch refusal, and independent call snapshots.
See the module README for the exact command. No main-harness test result is claimed
for this isolated addition.

Executed verification:

```sh
python -m unittest discover -s examples/three_lane_probe -p 'test_*.py' -q
ruff check --select E,F,I,UP,B --target-version py312 --line-length 100 examples/three_lane_probe
ruff format --check --line-length 100 examples/three_lane_probe
git diff --check
```

Results: 11/11 tests pass; lint and formatting pass. A CLI subprocess export was
parsed as JSON and confirmed `PARTIAL` with one successful lane, two blocked lanes,
and two calls for handshake plus CRLF tamper. No health endpoint or local browser
workflow applies to this CLI-only addition; main app startup was not exercised.

**UI fidelity gate: blocked.** The Product Design URL-to-code workflow requires
desktop/mobile source capture and an interactive visual comparison before a faithful
UI reconstruction is handed off. Desktop capture succeeded. The available browser
surface did not provide a working mobile viewport capture; no 390 × 844 source
capture or matching local UI verification was completed. No UI clone is delivered.

Next concrete work is to capture the mobile source and remaining interaction states,
then port the UI against the existing harness API or an explicitly separate adapter.
An original Grok project export would additionally resolve server implementation
unknowns. Any changed source golden hash falsifies exact assembly agreement and must
be investigated before broadening the claim. Cloud behavior needs a separate adapter
contract and verification; it cannot be inferred from these offline tests.
