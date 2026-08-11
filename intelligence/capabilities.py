"""Capability protocol for intelligence providers."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from intelligence.contracts import (
    AskIn,
    AskOut,
    ClassifyIn,
    ClassifyOut,
    DigestIn,
    DigestOut,
    RecommendIn,
    RecommendOut,
    SummarizeIn,
    SummarizeOut,
)


@runtime_checkable
class IntelligenceProvider(Protocol):
    name: str

    def summarize(self, payload: SummarizeIn) -> SummarizeOut: ...

    def classify(self, payload: ClassifyIn) -> ClassifyOut: ...

    def digest(self, payload: DigestIn) -> DigestOut: ...

    def recommend(self, payload: RecommendIn) -> RecommendOut: ...

    def ask(self, payload: AskIn) -> AskOut: ...
