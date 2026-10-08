"""Count-only provider checks. Never generate text or rewrite a stored control."""

import asyncio
import json
import os
import re
from importlib.metadata import version

import tiktoken

from .artifacts import digest
from .conditions import TOKENIZER_HASH, tokenizer, verify_condition
from .models import TokenMeasurement, TokenParity
from .providers import (
    _adapt_claude_messages,
    _claude_input_tokens,
    _grok_prompt_text,
    _grok_token_count,
    _XaiTransport,
    claude_available,
    grok_available,
    grok_client_kwargs,
)


class UnsupportedTokenization(ValueError):
    """No supported count-only path; do not substitute another tokenizer."""


def payload_hash(payload):
    return digest(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())


class ProviderTokenCounter:
    """Use the generation adapter's injected transport in tests, never its generate().

    The cache lasts only for one experiment and keys exact messages and scope. This
    avoids repeating count requests for identical replicate inputs, not model calls.
    """

    def __init__(self, request, provider):
        self.request, self.provider = request, provider
        self.cache = {}

    async def count(self, messages, *, context_only):
        key = (context_only, tuple((m.role, m.content) for m in messages))
        if key not in self.cache:
            try:
                self.cache[key] = await self._count(messages, context_only=context_only)
            except Exception as exc:
                self.cache[key] = TokenMeasurement(
                    status="UNSUPPORTED" if isinstance(exc, UnsupportedTokenization) else "ERROR",
                    method=f"{self.request.provider}.count_only",
                    scope="context" if context_only else "assembled_input",
                    uncertainty="No usable provider count; no fallback tokenizer was used.",
                    error_type=type(exc).__name__,
                )
        return self.cache[key].model_copy(deep=True)

    async def _count(self, messages, *, context_only):
        request = self.request
        provider = request.provider
        text = messages[0].content
        if provider in ("mock", "openai"):
            if provider == "openai" and (
                not re.fullmatch(r"gpt-(?:4o|4\.1)(?:-\d{4}-\d{2}-\d{2})?", request.model)
                or tiktoken.encoding_name_for_model(request.model) != "o200k_base"
            ):
                raise UnsupportedTokenization()
            texts = [text] if context_only else [m.content for m in messages]
            count = await asyncio.to_thread(
                lambda: sum(len(tokenizer().encode(value)) for value in texts)
            )
            return TokenMeasurement(
                status="COUNTED",
                tokens=count,
                method="bundled_tiktoken.encode_each_text",
                scope="context_text" if context_only else "sum_of_message_texts",
                payload_sha256=payload_hash(texts),
                tokenizer="o200k_base",
                tokenizer_sha256=TOKENIZER_HASH,
                tokenizer_version=version("tiktoken"),
                uncertainty=(
                    "Mock fixture only; no provider tokenizer or model was verified."
                    if provider == "mock"
                    else "Local encoding mapping; provider framing and alias drift unverified."
                ),
            )
        if provider == "grok":
            factory = getattr(self.provider, "client_factory", None)
            if not factory and (not request.cloud_consent or not grok_available()):
                raise UnsupportedTokenization()
            client = (factory or _XaiTransport)(**grok_client_kwargs(request.timeout_seconds))
            payload = text if context_only else _grok_prompt_text(messages)
            try:
                count = _grok_token_count(
                    await client.tokenize_text(text=payload, model=request.model)
                )
            finally:
                await client.close()
            return TokenMeasurement(
                status="COUNTED",
                tokens=count,
                method="xai.tokenize.tokenize_text",
                scope="context_text" if context_only else "role_labeled_text_v1",
                payload_sha256=payload_hash(payload),
                tokenizer=f"xai:{request.model}",
                tokenizer_version=None,
                uncertainty="Server tokenizer revision unknown; chat-template overhead excluded.",
            )
        if provider == "claude":
            factory = getattr(self.provider, "client_factory", None)
            if not factory and (not request.cloud_consent or not claude_available()):
                raise UnsupportedTokenization()
            from anthropic import AsyncAnthropic

            # A raw-text endpoint is unavailable. Use identical user wrappers for
            # the isolated contexts, and the real adapter's conversion for full input.
            if context_only:
                system, turns = None, [{"role": "user", "content": text}]
            else:
                system, turns = _adapt_claude_messages(messages)
            payload = {"model": request.model, "messages": turns}
            if system is not None:
                payload["system"] = system
            client = (factory or AsyncAnthropic)(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                base_url="https://api.anthropic.com",
                max_retries=0,
                timeout=request.timeout_seconds,
            )
            try:
                count = _claude_input_tokens(await client.messages.count_tokens(**payload))
            finally:
                await client.close()
            if type(count) is not int or count < 0:
                raise ValueError("Invalid token count")
            return TokenMeasurement(
                status="COUNTED",
                tokens=count,
                method="anthropic.messages.count_tokens",
                scope="isolated_user_message_estimate"
                if context_only
                else "adapted_messages_estimate",
                payload_sha256=payload_hash(payload),
                tokenizer=f"anthropic:{request.model}",
                uncertainty=(
                    "Estimate includes message formatting and possible system-added tokens; "
                    "not an exact raw-text or billed count. Server tokenizer revision unavailable."
                ),
            )
        if provider == "ollama":
            # No generation fallback: prompt_eval_count requires a model call.
            payload = text if context_only else "\n".join(m.content for m in messages)
            count = await self.provider._tokenize(payload, request.timeout_seconds)
            if count is None:
                raise UnsupportedTokenization()
            return TokenMeasurement(
                status="COUNTED",
                tokens=count,
                method="ollama./api/tokenize",
                scope="context_text" if context_only else "newline_joined_text_v1",
                payload_sha256=payload_hash(payload),
                tokenizer=f"ollama:{request.model}",
                uncertainty="Optional endpoint; tokenizer revision and chat template unverified.",
            )
        raise UnsupportedTokenization()


def compare_counts(left, right):
    if "ERROR" in (left.status, right.status):
        return "ERROR"
    if "UNSUPPORTED" in (left.status, right.status):
        return "UNSUPPORTED"
    if left.tokens is None or right.tokens is None:
        return "ERROR"
    if (left.method, left.scope, left.tokenizer, left.tokenizer_sha256, left.tokenizer_version) != (
        right.method,
        right.scope,
        right.tokenizer,
        right.tokenizer_sha256,
        right.tokenizer_version,
    ):
        return "ERROR"
    return "MATCHED" if left.tokens == right.tokens else "MISMATCHED"


async def measure_pair(request, full, control, counter, *, replay=False):
    """Evidence binds both texts and inputs; no baseline count is a control match."""
    for run in (full, control):
        verify_condition(run.condition)
    left, right = full.condition, control.condition
    measurements = []
    # One timeout for the whole pair, no retries or unbounded search for a match.
    try:
        async with asyncio.timeout(request.timeout_seconds):
            for context_only in (True, False):
                for condition in (left, right):
                    messages = condition.messages[:1] if context_only else condition.messages
                    measurements.append(await counter.count(messages, context_only=context_only))
    except TimeoutError:
        pass
    while len(measurements) < 4:
        measurements.append(
            TokenMeasurement(
                status="ERROR",
                method="preflight_timeout",
                scope="unmeasured",
                uncertainty="Count-only preflight timed out; parity is unavailable.",
                error_type="TimeoutError",
            )
        )
    lc, rc, li, ri = measurements
    context_status, input_status = compare_counts(lc, rc), compare_counts(li, ri)
    # Frozen handshake transcripts intentionally retain different generated replies.
    frozen_handshake = replay and request.delivery_mode == "USER_PASTE_WITH_HANDSHAKE"
    allowed = context_status == "MATCHED" and (
        input_status == "MATCHED" or (frozen_handshake and input_status == "MISMATCHED")
    )
    return TokenParity(
        provider=request.provider,
        model=request.model,
        replicate_index=full.replicate_index,
        injector_run_id=full.run_id,
        control_run_id=control.run_id,
        injector_sha256=digest(left.messages[0].content.encode()),
        control_sha256=digest(right.messages[0].content.encode()),
        injector_prompt_hash=left.prompt_hash,
        control_prompt_hash=right.prompt_hash,
        context_status=context_status,
        input_status=input_status,
        injector_context=lc,
        control_context=rc,
        injector_input=li,
        control_input=ri,
        generation_allowed=allowed,
        input_phase="FROZEN_FINAL_PROMPT" if replay else "INITIAL",
        note=(
            "Equality applies only to the recorded scopes, not exact total provider input. "
            "Generated handshake replies are not length controlled; frozen handshake replay "
            "requires context parity only. Matching does not establish injector effectiveness."
        ),
    )
