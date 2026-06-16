import json
from typing import Any

from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode, fallback_interpretation


def strict_ai_json_schema() -> dict[str, Any]:
    schema = AIInterpretation.model_json_schema()
    schema["additionalProperties"] = False
    return {
        "type": "json_schema",
        "name": "cb_failed_ai_interpretation",
        "strict": True,
        "schema": schema,
    }


class AIInterpreter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._daily_token_estimate = 0

    def interpret(self, payload: dict[str, Any]) -> tuple[AIInterpretation, str | None, int]:
        if not self.settings.ai_enabled:
            return fallback_interpretation(AIReasonCode.AI_DISABLED, "AI is disabled."), None, 0
        if not self.settings.openai_api_key:
            return fallback_interpretation(AIReasonCode.AI_DISABLED, "OPENAI_API_KEY is not configured."), None, 0
        if self._estimated_cost_usd() >= self.settings.ai_daily_cost_limit_usd:
            return fallback_interpretation(AIReasonCode.AI_LOW_CONFIDENCE, "AI daily cost limit reached."), None, 0

        primary, tokens = self._call_model(self.settings.openai_model_primary, payload)
        self._daily_token_estimate += tokens
        if primary and primary.confidence >= self.settings.ai_confidence_fallback_threshold:
            return primary, self.settings.openai_model_primary, tokens

        fallback, fallback_tokens = self._call_model(self.settings.openai_model_fallback, payload)
        self._daily_token_estimate += fallback_tokens
        if fallback:
            return fallback, self.settings.openai_model_fallback, tokens + fallback_tokens
        return fallback_interpretation(AIReasonCode.AI_SCHEMA_FAILURE, "AI failed or returned invalid schema."), None, tokens + fallback_tokens

    def _call_model(self, model: str, payload: dict[str, Any]) -> tuple[AIInterpretation | None, int]:
        for _ in range(max(1, self.settings.ai_max_retries + 1)):
            try:
                from openai import OpenAI

                client = OpenAI(api_key=self.settings.openai_api_key, timeout=self.settings.ai_timeout_seconds)
                response = client.responses.create(
                    model=model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "Interpret CB Failed operational correction comments. "
                                "Rules and dictionaries run before and after you. "
                                "Use only the sanitized fields provided. "
                                "Do not invent NPI, CBCode, provider names, sources, or recommended values. "
                                "A pure 10-digit number is an NPI candidate, not a CBCode. "
                                "ADD TO GE by itself means the provider/NPI needs GE or USAP setup; do not turn it into CHANGE_TICKET unless the same row explicitly says to change, correct, replace, or switch the ticket/provider. "
                                "Phrases like 'pending addition of correct provider/surgeon NAME with NPI <10-digit NPI>' identify a corrected target provider; extract the target name and NPI as CHANGE_TICKET with pending USAP/CBCode, not as pure ADD_TO_GE. "
                                "If a change-ticket row has a 10-digit NPI but no real CBCode, return the NPI and set target_cbcode to null. "
                                "Only extract values explicitly present in the text; downstream validation decides final recommendations. "
                                "Return strict JSON only."
                            ),
                        },
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
                    ],
                    text={"format": strict_ai_json_schema()},
                )
                raw = getattr(response, "output_text", "") or "{}"
                usage = getattr(response, "usage", None)
                token_estimate = int(getattr(usage, "total_tokens", 0) or len(raw) / 4)
                return AIInterpretation.model_validate_json(raw), token_estimate
            except (ValidationError, Exception):
                continue
        return None, 0

    def _estimated_cost_usd(self) -> float:
        return self._daily_token_estimate * 0.000001

    @staticmethod
    def manual_review_from_invalid() -> AIInterpretation:
        return AIInterpretation(
            action=AIAction.MANUAL_REVIEW,
            reason_code=AIReasonCode.AI_SCHEMA_FAILURE,
            target_provider_name=None,
            target_npi=None,
            target_cbcode=None,
            requires_add_to_ge=False,
            is_pending_usap=False,
            confidence=0,
            needs_manual_review=True,
            explanation="AI schema validation failed.",
        )
