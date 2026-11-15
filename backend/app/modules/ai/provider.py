import json

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from app.modules.ai.service import ConversationAnalysisOutput

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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
        with OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            timeout=timeout_seconds,
        ) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt["system"]},
                    {"role": "user", "content": prompt["user"]},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                extra_body={"reasoning": {"enabled": True}},
            )
    except OpenAIError as exc:
        raise AIProviderError("The AI provider request failed") from exc

    try:
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise TypeError("response content is not text")
        return ConversationAnalysisOutput.model_validate(json.loads(content))
    except (IndexError, KeyError, TypeError, ValueError, ValidationError) as exc:
        raise AIProviderError(
            "The AI provider returned an invalid conversation analysis"
        ) from exc