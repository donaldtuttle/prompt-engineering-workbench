"""Versioned deterministic inputs. No network access or runtime artifact repair."""

import base64
import json
from functools import lru_cache
from pathlib import Path

import tiktoken

from .artifacts import digest
from .models import Condition, Message

TOKENIZER_HASH = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
HANDSHAKE = (
    "Complete any activation or readiness handshake specified by the preceding context. "
    "If none is specified, state READY. Do not answer the experiment task yet."
)


@lru_cache(maxsize=1)
def tokenizer():
    # Construct from vendored bytes. Never call tiktoken's downloading constructor.
    data = (
        Path(__file__).resolve().parent.parent / "reference/tokenizers/o200k_base.tiktoken"
    ).read_bytes()
    if digest(data) != TOKENIZER_HASH:
        raise ValueError("Bundled tokenizer integrity mismatch")
    ranks = {
        base64.b64decode(token): int(rank)
        for token, rank in (line.split() for line in data.splitlines())
    }
    # Pattern from tiktoken 0.14.0 o200k_base. The constructor is inspected, not called.
    pattern = "|".join(
        [
            r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
            r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
            r"\p{N}{1,3}",
            r" ?[^\s\p{L}\p{N}]+[\r\n/]*",
            r"\s*[\r\n]+",
            r"\s+(?!\S)",
            r"\s+",
        ]
    )
    return tiktoken.Encoding(
        "workbench-o200k-base", pat_str=pattern, mergeable_ranks=ranks, special_tokens={}
    )


def serialize_messages(messages) -> bytes:
    return json.dumps(
        [m.model_dump() for m in messages], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def with_messages(condition, messages):
    payload = serialize_messages(messages)
    return condition.model_copy(
        update={
            "messages": tuple(messages),
            "prompt_hash": digest(payload),
            "prompt_byte_length": len(payload),
        }
    )


def verify_condition(condition):
    payload = serialize_messages(condition.messages)
    if digest(payload) != condition.prompt_hash or len(payload) != condition.prompt_byte_length:
        raise ValueError("Stored prompt hash or length mismatch")


def assemble(task, snapshot=None, *, kind=None, delivery_mode="SYSTEM_SLOT"):
    kind = kind or ("FULL_INJECTOR" if snapshot else "BASELINE")
    context = None
    metadata = None
    if kind != "BASELINE":
        if snapshot is None or snapshot.identity.status != "VALID":
            raise ValueError("Invalid injector: treatment/control blocked")
        raw = base64.b64decode(snapshot.bytes_base64, validate=True)
        context = raw.decode("utf-8")
        if kind == "NEUTRAL_LENGTH_CONTROL":
            enc = tokenizer()
            target = len(enc.encode(context))
            # A content-specificity comparator, not a claim of semantic inertness.
            context = " stone" * target
            actual = len(enc.encode(context))
            if actual != target:
                raise ValueError("Neutral control token-count invariant failed")
            metadata = {
                "generator": "repeated-stone-v1",
                "tokenizer": "o200k_base",
                "tokenizer_sha256": TOKENIZER_HASH,
                "target_tokens": target,
                "control_tokens": actual,
                "control_sha256": digest(context.encode()),
                "control_bytes": len(context.encode()),
                "reference_bytes": len(raw),
                "reference_sha256": snapshot.identity.sha256,
                "match_scope": "context text only; excludes protocol and role overhead",
                "semantic_neutrality": "NOT_ESTABLISHED",
            }
    messages = []
    if context is not None:
        role = "system" if delivery_mode == "SYSTEM_SLOT" else "user"
        messages.append(Message(role=role, content=context))
    messages.append(
        Message(
            role="user",
            content=(HANDSHAKE if delivery_mode == "USER_PASTE_WITH_HANDSHAKE" else task),
        )
    )
    condition = Condition(
        condition_id=kind,
        delivery_mode=delivery_mode,
        injector=snapshot.identity if snapshot and kind == "FULL_INJECTOR" else None,
        messages=(),
        prompt_hash="",
        prompt_byte_length=0,
        control_metadata=metadata,
    )
    return with_messages(condition, messages)
