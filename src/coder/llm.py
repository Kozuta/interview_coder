"""Клиент LLM (OpenAI-совместимый API, в т.ч. DeepSeek)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# .env из корня репозитория (на уровень выше src/coder)
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

DEFAULT_DEEPSEEK_BASE = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"

SYSTEM = (
    "Ты аналитик UX/CX-исследований. "
    "Отвечай строго валидным json без markdown и без пояснений вне json."
)


def _normalize_base_url(url: str | None) -> str | None:
    if not url:
        return None
    u = url.rstrip("/")
    if "deepseek.com" in u and not u.endswith("/v1"):
        # OpenAI SDK добавляет пути к base; для DeepSeek оба варианта работают
        pass
    return u


def _is_deepseek(base_url: str | None) -> bool:
    return bool(base_url and "deepseek" in base_url.lower())


def get_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "Задайте DEEPSEEK_API_KEY или OPENAI_API_KEY в .env (корень проекта coder)"
        )
    return key


def get_base_url() -> str | None:
    return _normalize_base_url(
        os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    )


def resolve_model(config_model: str | None = None) -> str:
    """Имя модели: project.yaml → LLM_MODEL в .env → deepseek-chat / gpt-4o-mini."""
    if config_model:
        return config_model
    env_model = os.getenv("LLM_MODEL")
    if env_model:
        return env_model
    if _is_deepseek(get_base_url()):
        return DEFAULT_DEEPSEEK_MODEL
    return "gpt-4o-mini"


def get_client() -> OpenAI:
    return OpenAI(api_key=get_api_key(), base_url=get_base_url())


def unwrap_list(result: Any, key: str) -> list:
    """Extract a list from an LLM result regardless of whether it returned
    {key: [...]} or a bare [...] directly."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get(key, [])
    return []


def _parse_json_content(content: str) -> Any:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # LLM sometimes wraps JSON in prose — try to extract the first object or array
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        m = re.search(pattern, content)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

    truncated = len(content) > 500
    hint = " (похоже, ответ обрезан — превышен лимит токенов)" if truncated else ""
    # Re-parse to get the exact json error position for diagnostics
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Ошибка парсинга JSON{hint}: {e}\n---\n{content[-500:]}") from e
    raise RuntimeError(f"Ошибка парсинга JSON{hint}:\n---\n{content[-500:]}")


def chat_json(
    client: OpenAI,
    model: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> Any:
    model = resolve_model(model)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    try:
        response = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        print(f"[llm] json_object mode не поддерживается ({e}), повтор без response_format")
        response = client.chat.completions.create(**kwargs)

    choice = response.choices[0]
    content = choice.message.content or "{}"
    if not content.strip():
        raise RuntimeError(
            f"Пустой ответ модели {model}. Попробуйте deepseek-chat или увеличьте max_tokens."
        )
    if getattr(choice, "finish_reason", None) == "length":
        raise RuntimeError(
            f"TOKEN_LIMIT: модель {model} обрезала ответ — превышен лимит токенов. "
            "Уменьшите чанк или передайте меньше данных."
        )
    return _parse_json_content(content)
