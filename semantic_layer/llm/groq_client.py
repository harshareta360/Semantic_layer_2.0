from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


class GroqLLMClient:
    """Minimal Groq chat-completions client (OpenAI-compatible HTTP API).

    Pattern aligned with Nora_ent nl2query-api shared.llm_client.GroqLLMClient.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model = (
            model
            or os.getenv("GROQ_MODEL")
            or os.getenv("MODEL")
            or "openai/gpt-oss-120b"
        )
        self.base_url = os.getenv(
            "GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions"
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def call_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_object: bool = True,
    ) -> dict[str, Any]:
        if not self.api_key:
            return {"error": "GROQ_API_KEY is not set"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_object:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                self.base_url, json=payload, headers=headers, timeout=60
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            body = getattr(e.response, "text", "") if e.response is not None else ""
            return {"error": f"HTTP Error: {e} - Response: {body}"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Request Error: {e}"}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Unexpected Error: {e}"}

    @staticmethod
    def extract_content(resp: dict[str, Any]) -> str:
        if "error" in resp:
            raise RuntimeError(str(resp["error"]))
        if "choices" in resp and resp["choices"]:
            return str(resp["choices"][0]["message"]["content"])
        if "content" in resp:
            return str(resp["content"])
        raise RuntimeError(f"Unexpected LLM response structure: {resp}")
