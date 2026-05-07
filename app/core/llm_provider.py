"""
Model-agnostic LLM abstraction.
Swap providers by changing LLM_PROVIDER in .env — zero engine code changes.

Supported providers:
  openai      — OpenAI GPT-4o via openai 2.x SDK
  anthropic   — Anthropic Claude via anthropic 0.97 SDK
  openrouter  — Any model via OpenRouter (openai SDK, different base_url)
  ollama      — Local models (Qwen, Llama, Mistral) via Ollama REST API
  azure       — Azure OpenAI via openai 2.x AzureAsyncOpenAI client
"""
from typing import Optional
from app.config import settings


def get_llm_client():
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=settings.openai_api_key)

    elif provider == "anthropic":
        from anthropic import AsyncAnthropic
        return AsyncAnthropic(api_key=settings.anthropic_api_key)

    elif provider == "openrouter":
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )

    elif provider == "ollama":
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key="ollama",
            base_url=f"{settings.ollama_base_url}/v1",
        )

    elif provider == "azure":
        from openai import AsyncAzureOpenAI
        return AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            f"Valid options: openai, anthropic, openrouter, ollama, azure"
        )


def get_model_name() -> str:
    provider = settings.llm_provider.lower()
    mapping = {
        "openai": settings.openai_model,
        "anthropic": settings.anthropic_model,
        "openrouter": settings.openrouter_model,
        "ollama": settings.ollama_model,
        "azure": settings.azure_openai_deployment,
    }
    return mapping.get(provider, settings.openai_model)


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
        # OpenAI, OpenRouter, Ollama — all use chat.completions.create
        kwargs = dict(
            model=get_model_name(),
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
