"""Token-cost inspection for QOFT's core notation, using the workbench's
own hash-verified o200k_base tokenizer (no network, same tokenizer the
harness uses for NEUTRAL_LENGTH_CONTROL matching)."""
from workbench.conditions import tokenizer

enc = tokenizer()

samples = {
    "Master equation":        "Ξ(ψ) = ψᴽ ⊕ Γ(ψ)",
    "Xi alone":                "Ξ",
    "Reflexive projection":    "ψᴽ",
    "Gradient":                "Γ(ψ)",
    "Fusion operator":         "⊕",
    "Junction mark":           "⟐",
    "Junction state (compressed)": "Ξ⟐ψᴽ",
    "Same, spelled out":       "Xi-Junction-Psi-Reflexive",
    "Plain-English gloss":     "the reflexive projection of psi",
}

print(f"{'Sample':<32} {'chars':>6} {'tokens':>7}  token pieces (raw bytes)")
print("-" * 110)
for label, text in samples.items():
    ids = enc.encode(text)
    pieces = [enc.decode_single_token_bytes(i) for i in ids]
    print(f"{label:<32} {len(text):>6} {len(ids):>7}  {pieces}")
