"""Provider factory."""
from __future__ import annotations

from intelligence.capabilities import IntelligenceProvider
from intelligence.providers.minimax import MinimaxProvider
from intelligence.providers.mock import MockProvider
from intelligence.providers.openclaw import OpenClawProvider
from pipeline.settings import get_settings


def create_provider() -> IntelligenceProvider:
    settings = get_settings()
    name = settings.resolved_provider()
    if name == "minimax":
        return MinimaxProvider(
            api_key=settings.resolved_minimax_api_key(),
            base_url=settings.minimax_base_url,
            model=settings.minimax_model,
        )
    if name == "openclaw":
        return OpenClawProvider(
            gateway_url=settings.openclaw_gateway_url,
            token=settings.openclaw_token,
        )
    if name == "spagent":
        # Reserved — fall back to mock until wired
        return MockProvider()
    return MockProvider()
