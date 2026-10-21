"""Live smoke test for Nebius Token Factory with real credentials."""

import os

import pytest
from praxis_core.models.config import ModelConfig
from praxis_core.models.providers.base import NormalizedCompletionRequest
from praxis_core.models.providers.nebius import NebiusTokenFactoryAdapter


@pytest.mark.skipif(
    not os.environ.get("MODEL_API_KEY"),
    reason="MODEL_API_KEY environment variable not set; skipping live smoke test",
)
def test_live_nebius_inference_smoke():
    api_key = os.environ["MODEL_API_KEY"]
    base_url = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")

    config = ModelConfig(
        key="nemotron-3.5-lightning",
        display_name="Nemotron 3.5 Lightning",
        provider="nebius",
        model_id="nvidia/Nemotron-3_5-Lightning",
        temperature=0.1,
        max_output_tokens=50,
    )

    adapter = NebiusTokenFactoryAdapter(config=config, api_key=api_key, base_url=base_url)
    req = NormalizedCompletionRequest(
        messages=[{"role": "user", "content": "Respond with the word: PONG"}],
        max_tokens=30,
    )

    resp = adapter.invoke(req)

    assert resp.text != ""
    assert resp.provider == "nebius"
    assert resp.model == "nvidia/Nemotron-3_5-Lightning"
    assert resp.usage.total_tokens > 0
