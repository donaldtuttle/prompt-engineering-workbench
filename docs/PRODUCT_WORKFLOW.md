# Product workflow — v0.2.1

1. Start the server locally and open http://127.0.0.1:8765 on the same computer.
2. Enter a probe, title, and probe ID. Text is preserved as submitted. Browser textarea newline
   handling is standard; use the JSON API when a frozen probe requires exact CRLF strings.
3. Select a local artifact and inspect its integrity status, byte count, and hash.
4. Choose delivery mode and 1–4 replicates. A valid artifact creates three conditions per replicate.
   No artifact creates baseline only. Invalid context blocks injector and control lanes.
5. Keep Mock for fixture-only work. Ollama appears when a loopback server has installed models and
   needs no API key. OpenAI appears only when enabled on the server with a key; selecting it requires
   an explicit model string and cloud consent, and the UI states that charges apply.
6. Set sampling controls, timeout, retries, and concurrency. Blank sampling values are omitted.
   Handshake mode adds a call to every lane. The preview shows calls before retries.
7. Run. Inspect independent raw outputs, phase timing, model strings, statuses, and final prompt hashes.
   Expand handshake output where present. A successful lane is execution status, not an evaluation.
8. Export JSON or JSONL. It includes preserved artifact/manifest bytes, condition messages,
   initial/final hashes, settings, phase calls, results, and replay lineage when relevant.
9. Reload/open history. v1 records keep their original schema and recorded artifact state.
10. Reuse setup to build a fresh v2 run using current files; review its settings and cloud selection.
11. Replay snapshot for a terminal v2 record. The server verifies stored inputs/configuration and
    reruns the exact stored final messages. Handshake replies are frozen in that replay.
12. Shut down with Ctrl+C before backups/upgrades. Unfinished work becomes INTERRUPTED, never
    an automatic resubmission.

Condition labels are visible. This comparison view is for inspection; it does not collect
blinded judgments or score evidence. The audit outcome stays INSUFFICIENT_EVIDENCE.
