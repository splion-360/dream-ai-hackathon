from __future__ import annotations

from math_tutor.domain import Difficulty

_ADVANCED_SIGNALS = (
    "abstract algebra",
    "complex analysis",
    "differential equation",
    "eigenvalue",
    "fourier",
    "group theory",
    "heat equation",
    "measure theory",
    "partial differential",
    "quantum",
    "stochastic",
    "taylor series",
    "tensor",
    "topology",
)

_FOUNDATIONAL_SIGNALS = (
    "add two",
    "addition",
    "arithmetic",
    "basic fraction",
    "counting",
    "decimal",
    "fraction",
    "long division",
    "multiplication",
    "perimeter",
    "place value",
    "subtraction",
    "times table",
)


def infer_difficulty(prompt: str) -> Difficulty:
    """Route a prompt with a small, deterministic hackathon heuristic."""
    normalized = " ".join(prompt.casefold().split())
    if any(signal in normalized for signal in _ADVANCED_SIGNALS):
        return Difficulty.ADVANCED
    if any(signal in normalized for signal in _FOUNDATIONAL_SIGNALS):
        return Difficulty.FOUNDATIONAL
    return Difficulty.INTERMEDIATE
