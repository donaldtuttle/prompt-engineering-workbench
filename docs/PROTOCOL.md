# v0.2.0 experiment and replay protocol

Classification: engineering harness / experimental protocol. Status: DEVELOP.
The workbench does not implement the QOFT fusion operator or certify injector activation.
Its evidence boundary is recorded inputs, provider outputs, and software checks.

## Conditions and delivery

For an artifact, every replicate includes BASELINE, FULL_INJECTOR, and NEUTRAL_LENGTH_CONTROL.
Invalid artifact integrity blocks the latter two before a provider is called.

| Delivery mode | Baseline | Full/control context |
| --- | --- | --- |
| SYSTEM_SLOT | user(task) | system(context), user(task) |
| USER_PASTE | user(task) | user(context), user(task) |
| USER_PASTE_WITH_HANDSHAKE | user(readiness prompt); assistant(reply); user(task) | user(context), user(readiness prompt); assistant(reply); user(task) |

Semicolons separate provider calls. Context and task in USER_PASTE are separate user messages;
there is no invented assistant acknowledgement. That is an explicit harness treatment, not
an assertion that every chat product handles adjacent user messages identically.

The exact shared readiness prompt is:

> Complete any activation or readiness handshake specified by the preceding context. If none is specified, state READY. Do not answer the experiment task yet.

The final task is withheld during handshake generation. Baseline also gets a preparation
call, so the treatment is not the only arm with an extra generated turn. Handshake replies
are unscored raw output; they are not proof that an activation contract passed.
Incomplete preparation output prevents a task call. A failed task preserves its completed
handshake result and assembled final input.

Each lane has isolated history. No lane sees another lane's response. Replicates use
zero-based indices and the same declared settings; there is no hidden seed increment,
condition randomization, or adaptive stopping.

## Neutral length control

Generator repeated-stone-v1 constructs the text `" stone"` repeated to exactly match the
reference context's token count under pinned o200k_base data. A second encode verifies the
match. The count excludes role/protocol overhead and generated handshake replies.
The restored 80,140-byte QOFT artifact has 14,224 context tokens under this tokenizer.

Metadata records generator, tokenizer identity/hash, reference SHA-256, input/control byte
lengths, both token counts, and control text SHA-256. Actual control text is preserved in the
condition messages. The original artifact identity remains at experiment level; the neutral
condition does not falsely label that original injector as its delivered context.

This is a named content comparator. Repetition and semantic content can themselves affect
models; semantic neutrality is NOT_ESTABLISHED. The text is not byte matched.
An explicit model-specific tokenizer check is required before interpreting live comparisons.
The returned provider token usage measures total calls, including task/protocol overhead;
it is distinct from the construction count. Generated handshake lengths need not match.

## Settings and hashes

- Sampling records temperature, top_p, seed, and max_output_tokens. Null temperature/top_p
  means omitted/provider default, not a known numerical default.
- A null seed is not an inferred provider seed. This OpenAI Responses adapter rejects explicit
  seeds; mock records a fixture seed without claiming random sampling.
- model records the exact requested string; resolved_model captures the exact string returned.
  A provider returning an alias leaves immutable backend identity unresolved.
- provider_versions records the installed SDK versions.
- configuration_hash binds provider, requested model, sampling, delivery, replicate index,
  timeout/retry/concurrency settings, SDK versions, API mode, disabled tracing/storage, and tools.
- messages-json-v1 remains SHA-256 of UTF-8 JSON, ensure_ascii=False, compact separators,
  ordered messages and ordered role/content keys. New delivery behavior does not change
  the serializer's version.
- condition.prompt_hash binds the initially submitted message list. final_condition.prompt_hash
  binds the actual task-call input after any generated handshake.
- calls records phase, attempt number, prompt hash, timing, normalized result, returned model,
  usage when supplied, response status/ID, or exception type.

Retries repeat the protocol and preserve every recorded call. A timeout covers the entire
attempt, including its two phases and persistence. SDK/client automatic retries are disabled.
run.result refers to the final task result; total observed usage is the sum of non-null
call results, not just run.result. A timeout can incur provider work without returning usage,
so missing call usage cannot be treated as zero.

## Snapshot replay

Replay creates a new ID with replay_of_experiment_id, per-run parent IDs, and
replay_mode=FROZEN_FINAL_PROMPT. It reads stored snapshots and messages, without loading the
current reference files or regenerating a control.

Before admission to execution it verifies stored task/artifact/manifest hashes, prompt hashes
and byte lengths, configuration hashes, request/run agreement, and unchanged SDK versions.
For a handshake experiment, it freezes the original final prompt including the original
assistant handshake reply. It reruns the task call only. Thus it tests a fixed model input;
a new handshake experiment is created with Reuse setup.

An unfinished handshake without a stored final prompt cannot be replayed. BLOCKED lanes
stay blocked. Unknown schemas and legacy v1 records are refused for replay. Replay does not
guarantee output equality, model availability, or immutable provider identity.

## Evidence and remaining gates

Supported claim: the software preserves and routes the declared controlled inputs and records
responses under its tested runtime. Falsifier: a wire input differs from its stored message
sequence/hash, a blocked lane reaches a provider, a replay uses changed disk inputs, or an old
terminal record is changed by migration.

No scientific efficacy result follows from the shipped fixtures. Evaluation fields remain
null, resolution is INSUFFICIENT_EVIDENCE, and condition labels are visible. A future efficacy
study needs preregistered probes/endpoints, tokenizer suitability, validated activation scoring
when relevant, power/replicate planning, randomized execution policy, blinded evaluation, and
a justified control family. Ablations still require D4's persistence redesign.
