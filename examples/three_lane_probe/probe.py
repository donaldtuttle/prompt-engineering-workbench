"""Offline reconstruction of the public Three-Lane Probe's visible protocol.

This is an independent DEMO-only tool, not the workbench harness or Grok backend.
No network requests, QOFT artifact loading, or scientific evaluation occur here.
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from uuid import uuid4

TASK = (
    "A baker has 3 eggs. Each cake needs 2 eggs, and the order is for 4 cakes. "
    "How many more eggs are needed? Answer in one sentence."
)
DEMO = (
    "OFFLINE WORKBENCH FIXTURE v1\n"
    "This is a software-testing fixture, not the QOFT injector.\n"
    "Preserve the task exactly. No scientific or model-effectiveness claim is made.\n\n"
)
DEMO_SHA256 = "adb50bebae4e3576c2c96c70866f4d1357888c35b2e13d76d2c88383870fc541"
DEMO_BYTES = DEMO.encode("utf-8")
HANDSHAKE = (
    "Complete any activation or readiness handshake specified by the preceding "
    "context. If none is specified, state READY. Do not answer the experiment task yet."
)
CONDITIONS = ("BASELINE", "FULL_INJECTOR", "NEUTRAL_LENGTH_CONTROL")
DELIVERIES = ("SYSTEM_SLOT", "USER_PASTE", "USER_PASTE_WITH_HANDSHAKE")
# Exact fixed-fixture metadata recovered from the source client. Not a tokenizer.
SOURCE_DEMO_TOKENS = 40
CONTROL = " stone" * SOURCE_DEMO_TOKENS


def now():
    return datetime.now(UTC).isoformat()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def serialize_messages(messages):
    """Match the observed JS role/content insertion order and compact JSON."""
    return json.dumps(
        [{"role": m["role"], "content": m["content"]} for m in messages],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def prompt_hash(messages):
    return sha256(serialize_messages(messages))


def inspect_demo(raw):
    diagnostics = []
    if sha256(raw) != DEMO_SHA256:
        diagnostics.append("Full-file SHA-256 mismatch")
    if len(raw) != 168:
        diagnostics.append("Byte length mismatch")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        diagnostics.append("Artifact is not valid UTF-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        diagnostics.append("UTF-8 BOM is unsupported; bytes were not modified")
    if b"\r" in raw:
        diagnostics.append("DEMO bytes differ from the pinned LF fixture")
    return {
        "status": "INVALID" if diagnostics else "VALID",
        "sha256": sha256(raw),
        "byte_length": len(raw),
        "expected_sha256": DEMO_SHA256,
        "expected_byte_length": 168,
        "diagnostics": diagnostics,
        "source_reported_context_tokens": None if diagnostics else SOURCE_DEMO_TOKENS,
        "token_count_basis": "fixed source DEMO metadata; no runtime tokenization",
    }


def assemble(task, condition, delivery, raw=DEMO_BYTES):
    if condition not in CONDITIONS or delivery not in DELIVERIES:
        raise ValueError("Unknown condition or delivery mode")
    if not isinstance(task, str) or not task.strip() or len(task) > 4000:
        raise ValueError("Task must contain 1 to 4000 non-blank characters")
    context = None
    if condition != "BASELINE":
        if inspect_demo(raw)["status"] != "VALID":
            raise ValueError("Invalid DEMO: treatment/control blocked")
        context = raw.decode("utf-8") if condition == "FULL_INJECTOR" else CONTROL
    messages = []
    if context is not None:
        messages.append(
            {
                "role": "system" if delivery == "SYSTEM_SLOT" else "user",
                "content": context,
            }
        )
    messages.append(
        {
            "role": "user",
            "content": HANDSHAKE if delivery == "USER_PASTE_WITH_HANDSHAKE" else task,
        }
    )
    return messages


def fixture_call(messages, expected_hash, phase, condition):
    """Rehash at the fixture boundary and refuse changed messages."""
    started = now()
    wire_hash = prompt_hash(messages)
    if wire_hash != expected_hash:
        raise ValueError("Prompt hash mismatch; fixture call refused")
    # The original server's exact handshake output was not recovered.
    # READY is our explicit local fixture policy, never an activation verdict.
    if phase == "HANDSHAKE":
        response = "READY"
    else:
        response = json.dumps(
            {
                "kind": "OFFLINE_FIXTURE",
                "notice": "Synthetic acknowledgement. No model answered or evaluated this task.",
                "task_received": messages[-1]["content"],
                "message_count": len(messages),
                "injector_present": condition == "FULL_INJECTOR",
                "assembled_prompt_sha256": wire_hash,
                "fixture_seed": None,
            },
            ensure_ascii=False,
            indent=2,
        )
    return {
        "phase": phase,
        "messages": [dict(m) for m in messages],
        "prompt_hash": expected_hash,
        "fixture_boundary_hash": wire_hash,
        "hash_match": True,
        "started_at": started,
        "ended_at": now(),
        "response": response,
        "usage": None,
        "cost": None,
        "error_type": None,
    }


def run(task=TASK, delivery="SYSTEM_SLOT", tamper=False):
    # Validate before creating partial output, including when every context lane blocks.
    assemble(task, "BASELINE", delivery)
    raw = DEMO.encode("utf-8")
    if tamper:
        raw = raw.replace(b"\n", b"\r\n")
    artifact = inspect_demo(raw)
    experiment = {
        "schema_version": "three-lane-reconstruction-v1",
        "experiment_id": str(uuid4()),
        "created_at": now(),
        "source_url": "https://cactus-umbra-vivid-lunar.grok.me/",
        "classification": "DEVELOP; independent offline reconstruction",
        "evidence_scope": "SOFTWARE_FIXTURE_ONLY; no LLM or QOFT mechanism tested",
        "provider": "mock",
        "model": "reconstructed-fixture-v1",
        "resolved_model": None,
        "task": task,
        "task_sha256": sha256(task.encode("utf-8")),
        "delivery_mode": delivery,
        "artifact": artifact,
        "artifact_text": raw.decode("utf-8"),
        "evaluation": None,
        "resolution": "INSUFFICIENT_EVIDENCE",
        "runs": [],
    }
    for condition in CONDITIONS:
        lane = {"condition": condition, "calls": [], "result": None}
        experiment["runs"].append(lane)
        if condition != "BASELINE" and artifact["status"] != "VALID":
            lane.update(status="BLOCKED", errors=list(artifact["diagnostics"]))
            continue
        messages = assemble(task, condition, delivery, raw)
        lane["initial_prompt_hash"] = prompt_hash(messages)
        if delivery == "USER_PASTE_WITH_HANDSHAKE":
            call = fixture_call(messages, prompt_hash(messages), "HANDSHAKE", condition)
            lane["calls"].append(call)
            messages = messages + [
                {"role": "assistant", "content": call["response"]},
                {"role": "user", "content": task},
            ]
        call = fixture_call(messages, prompt_hash(messages), "TASK", condition)
        lane["calls"].append(call)
        lane.update(status="SUCCEEDED", result=call["response"], errors=[])
    experiment["status"] = (
        "COMPLETED" if all(r["status"] == "SUCCEEDED" for r in experiment["runs"]) else "PARTIAL"
    )
    experiment["ended_at"] = now()
    return experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default=TASK)
    parser.add_argument("--delivery", choices=DELIVERIES, default=DELIVERIES[0])
    parser.add_argument("--tamper-crlf", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args.task, args.delivery, args.tamper_crlf)
    except ValueError as exc:
        parser.error(str(exc))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
