from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.schemas.ai import AIInterpretation
from backend.app.services.ai_interpreter import AIInterpreter, strict_ai_json_schema


def test_strict_schema_forbids_extra_properties() -> None:
    schema = strict_ai_json_schema()["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) >= {
        "action",
        "reason_code",
        "target_provider_name",
        "target_npi",
        "target_cbcode",
        "requires_add_to_ge",
        "is_pending_usap",
        "confidence",
        "needs_manual_review",
        "explanation",
    }


def test_pydantic_rejects_invalid_ai_response() -> None:
    try:
        AIInterpretation.model_validate({"action": "BOGUS"})
    except ValidationError:
        assert True
    else:
        raise AssertionError("Invalid AI response should fail validation")


def test_ai_disabled_mode_returns_manual_review() -> None:
    settings = Settings()
    settings.ai_enabled = False
    result, model, tokens = AIInterpreter(settings).interpret({})
    assert result.action == "MANUAL_REVIEW"
    assert model is None
    assert tokens == 0


def test_ai_schema_failure_fallback(monkeypatch) -> None:
    settings = Settings()
    settings.ai_enabled = True
    settings.openai_api_key = "test"
    interpreter = AIInterpreter(settings)
    monkeypatch.setattr(interpreter, "_call_model", lambda model, payload: (None, 0))
    result, model, _ = interpreter.interpret({})
    assert result.action == "MANUAL_REVIEW"
    assert model is None

