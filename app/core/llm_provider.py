"""
Model-agnostic LLM abstraction.
Swap providers by changing LLM_PROVIDER in .env — zero engine code changes.

Supported providers:
  openai      — OpenAI GPT-4o via openai 2.x SDK
  anthropic   — Anthropic Claude via anthropic 0.97 SDK
  openrouter  — Any model via OpenRouter (openai SDK, different base_url)
  ollama      — Local models (Qwen, Llama, Mistral) via Ollama REST API
  azure       — Azure OpenAI via openai 2.x AzureAsyncOpenAI client
  modal       — Qwen 2.5 72B via vLLM on Modal A100 (OpenAI-compatible endpoint)
                Set MODAL_LLM_ENDPOINT after: modal deploy app_modal.py --env rag
"""
from typing import Optional
from langsmith import traceable
from app.config import settings


def _http_client():
    """Return an httpx.AsyncClient with SSL verification disabled when SSL_VERIFY=false."""
    if not settings.ssl_verify:
        import httpx
        return httpx.AsyncClient(verify=False)
    return None


def get_llm_client():
    provider = settings.llm_provider.lower()
    http_client = _http_client()

    if provider == "openai":
        from openai import AsyncOpenAI
        kwargs = {"api_key": settings.openai_api_key}
        if http_client:
            kwargs["http_client"] = http_client
        return AsyncOpenAI(**kwargs)

    elif provider == "anthropic":
        from anthropic import AsyncAnthropic
        kwargs = {"api_key": settings.anthropic_api_key}
        if http_client:
            kwargs["http_client"] = http_client
        return AsyncAnthropic(**kwargs)

    elif provider == "openrouter":
        from openai import AsyncOpenAI
        kwargs = {
            "api_key": settings.openrouter_api_key,
            "base_url": settings.openrouter_base_url,
        }
        if http_client:
            kwargs["http_client"] = http_client
        return AsyncOpenAI(**kwargs)

    elif provider == "ollama":
        from openai import AsyncOpenAI
        kwargs = {
            "api_key": "ollama",
            "base_url": f"{settings.ollama_base_url}/v1",
        }
        if http_client:
            kwargs["http_client"] = http_client
        return AsyncOpenAI(**kwargs)

    elif provider == "modal":
        from openai import AsyncOpenAI
        import httpx
        if not settings.modal_llm_endpoint:
            raise ValueError(
                "MODAL_LLM_ENDPOINT is not set. "
                "Deploy first: modal deploy app_modal.py --env rag "
                "then copy the printed URL into .env"
            )
        # 10-minute timeout — Modal cold start (A100 spin-up + vLLM load) can take 5+ min
        # follow_redirects=True — Modal returns 303 during cold start while container warms up
        modal_http = httpx.AsyncClient(timeout=600, verify=settings.ssl_verify, follow_redirects=True)
        return AsyncOpenAI(
            api_key="modal",
            base_url=f"{settings.modal_llm_endpoint.rstrip('/')}/v1",
            http_client=modal_http,
        )

    elif provider == "azure":
        from openai import AsyncAzureOpenAI
        kwargs = {
            "api_key": settings.azure_openai_api_key,
            "azure_endpoint": settings.azure_openai_endpoint,
            "api_version": settings.azure_openai_api_version,
        }
        if http_client:
            kwargs["http_client"] = http_client
        return AsyncAzureOpenAI(**kwargs)

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            f"Valid options: openai, anthropic, openrouter, ollama, azure, modal"
        )


def get_model_name() -> str:
    provider = settings.llm_provider.lower()
    mapping = {
        "openai":      settings.openai_model,
        "anthropic":   settings.anthropic_model,
        "openrouter":  settings.openrouter_model,
        "ollama":      settings.ollama_model,
        "azure":       settings.azure_openai_deployment,
        "modal":       settings.modal_llm_model,
    }
    return mapping.get(provider, settings.openai_model)


@traceable(run_type="llm", name="call_llm")
async def call_llm(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 4096,
    response_format: Optional[dict] = None,
) -> str:
    """
    Unified LLM call across all providers.
    Agents call this — never the provider SDK directly.
    Returns the text content of the response.
    """
    from app.core.rate_limiter import call_with_backoff

    provider = settings.llm_provider.lower()
    client = get_llm_client()

    if provider == "anthropic":
        system_msg = next(
            (m["content"] for m in messages if m["role"] == "system"), None
        )
        user_msgs = [m for m in messages if m["role"] != "system"]

        async def _call():
            resp = await client.messages.create(
                model=get_model_name(),
                max_tokens=max_tokens,
                system=system_msg or "You are a helpful assistant.",
                messages=user_msgs,
            )
            return resp.content[0].text

        return await call_with_backoff(_call)

    elif provider == "azure":
        kwargs = dict(
            model=settings.azure_openai_deployment,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format

        async def _call():
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content

        return await call_with_backoff(_call)

    else:
        # OpenAI, OpenRouter, Ollama, Modal — all use chat.completions.create
        kwargs = dict(
            model=get_model_name(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Modal/vLLM: skip response_format — xgrammar guided decoding crashes vLLM engine.
        # Qwen follows JSON instructions in the prompt without it (same as Anthropic path).
        if response_format and provider != "modal":
            kwargs["response_format"] = response_format

        async def _call():
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content

        return await call_with_backoff(_call)
