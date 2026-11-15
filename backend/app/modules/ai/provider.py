import json

import httpx
from pydantic import ValidationError

from app.modules.ai.service import ConversationAnalysisOutput

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class AIProviderError(RuntimeError):
    """The configured AI provider could not return a valid analysis."""


def analyze_with_openai(
    prompt: dict[str, str],
    *,
    api_key: str,
    model: str,
    timeout_seconds: float,
) -> ConversationAnalysisOutput:
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                OPENAI_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt["system"]},
                        {"role": "user", "content": prompt["user"]},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise AIProviderError("The AI provider request failed") from exc
    except ValueError as exc:
        raise AIProviderError("The AI provider returned invalid JSON") from exc

    try:
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("response content is not text")
        return ConversationAnalysisOutput.model_validate(json.loads(content))
    except (IndexError, KeyError, TypeError, ValueError, ValidationError) as exc:
        raise AIProviderError("The AI provider returned an invalid conversation analysis") from exc
