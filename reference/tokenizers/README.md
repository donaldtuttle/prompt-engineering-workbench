# Bundled tokenizer data

o200k_base.tiktoken was retrieved from the URL declared by the installed tiktoken 0.14.0
package, verified against that package's expected SHA-256, and bundled for offline operation.

Source: https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken

SHA-256: 446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d

Size: 3,613,922 bytes. The tiktoken MIT license is retained alongside it.
workbench/conditions.py checks the hash and builds the encoding locally with the matching
o200k pattern; it never invokes a constructor that downloads data. Special-token spellings
in arbitrary probe/context text are treated as ordinary text. No model-specific tokenizer
equivalence is inferred from the user's requested model string.
