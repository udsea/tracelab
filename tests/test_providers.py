import httpx
import pytest
from tracelab.models.domain import ProviderSettings
from tracelab.providers.base import HTTPProvider


@pytest.mark.parametrize("kind", ["openai_compatible", "anthropic"])
async def test_structured_provider_wire_contract(monkeypatch, kind):
    import json

    seen = []

    def handler(request):
        seen.append(request)
        response = (
            {"content": [{"type": "tool_use", "name": "record_analysis", "input": {"score": 0.5}}]}
            if kind == "anthropic"
            else {"choices": [{"message": {"content": '{"score":0.5}'}}]}
        )
        return httpx.Response(200, json=response)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    provider = HTTPProvider(
        ProviderSettings(
            id="p",
            name="Test",
            kind=kind,
            base_url="http://localhost:8080/v1",
            api_key_env="UNUSED",
        )
    )
    schema = {
        "type": "object",
        "properties": {"score": {"type": "number"}},
        "required": ["score"],
        "additionalProperties": False,
    }
    response = await provider.generate_structured(
        model="test", prompt="exact prompt", schema=schema, parameters={"max_tokens": 128}
    )
    body = json.loads(seen[0].content)
    assert body["messages"][0]["content"] == "exact prompt"
    assert response["raw"]
    assert "Authorization" not in str(response["request"])
    if kind == "anthropic":
        assert body["tools"][0]["input_schema"] == schema
        assert body["tool_choice"] == {"type": "tool", "name": "record_analysis"}
    else:
        assert body["response_format"]["json_schema"]["strict"]
    with pytest.raises(ValueError, match="Unsupported"):
        await provider.generate_structured(
            model="test", prompt="exact prompt", schema=schema, parameters={"messages": []}
        )
