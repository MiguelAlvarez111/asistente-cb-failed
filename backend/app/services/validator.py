from backend.app.schemas.ai import AIAction, AIInterpretation
from backend.app.schemas.dictionaries import DictionaryType
from backend.app.schemas.results import ValidationResult, ValidationStatus
from typing import Any

from backend.app.services.dictionary_loader import DictionaryIndex, resolve_effective_matches
from backend.app.services.npi_registry import get_npi_data


def _registry_full_name(npi_data: dict[str, str] | None) -> str | None:
    return npi_data.get("full_name") if npi_data else None


def _is_deactivated(value: str | None) -> bool:
    return bool(value and value.strip().upper() not in {"", "N", "NO", "0", "FALSE"})


def _role_dictionary_types(row: dict[str, Any] | None) -> tuple[set[DictionaryType] | None, set[DictionaryType] | None]:
    role = str((row or {}).get("type", "") or "").strip().lower()
    if role == "provider":
        return {DictionaryType.USAP_PROVIDERS}, {DictionaryType.REFERRING_PROVIDERS}
    if role == "surgeon":
        return {DictionaryType.REFERRING_PROVIDERS}, {DictionaryType.USAP_PROVIDERS}
    return None, None


def _is_surgeon(row: dict[str, Any] | None) -> bool:
    return str((row or {}).get("type", "") or "").strip().lower() == "surgeon"


def _lookup_matches(
    interpretation: AIInterpretation,
    index: DictionaryIndex,
    *,
    dictionary_types: set[DictionaryType] | None = None,
):
    if interpretation.action == AIAction.CHANGE_TICKET:
        if interpretation.target_cbcode:
            return index.lookup(cbcode=interpretation.target_cbcode, dictionary_types=dictionary_types)
        if interpretation.target_npi:
            return index.lookup(npi=interpretation.target_npi, dictionary_types=dictionary_types)
        if interpretation.target_provider_name:
            return index.lookup(provider_name=interpretation.target_provider_name, dictionary_types=dictionary_types)
        return []
    return index.lookup(
        npi=interpretation.target_npi,
        cbcode=interpretation.target_cbcode,
        provider_name=interpretation.target_provider_name,
        dictionary_types=dictionary_types,
    )


def validate_interpretation(interpretation: AIInterpretation, index: DictionaryIndex, row: dict[str, Any] | None = None) -> ValidationResult:
    if interpretation.reason_code.value == "MALFORMED_ROW":
        return ValidationResult(
            status=ValidationStatus.MALFORMED_ROW,
            details="Malformed row marker detected.",
            matches=[],
            npi_registry_name=None,
            needs_manual_review=True,
        )
    if interpretation.requires_add_to_ge or interpretation.action == AIAction.ADD_TO_GE:
        return ValidationResult(
            status=ValidationStatus.ADD_TO_GE_REQUIRED,
            details="Provider must be added to GE before completion.",
            matches=[],
            npi_registry_name=None,
            needs_manual_review=False,
        )

    preferred_types, fallback_types = _role_dictionary_types(row)
    role_mismatch = False
    raw_matches = _lookup_matches(interpretation, index, dictionary_types=preferred_types)
    if preferred_types is not None and not raw_matches:
        fallback_matches = _lookup_matches(interpretation, index, dictionary_types=fallback_types)
        if fallback_matches:
            raw_matches = fallback_matches
            role_mismatch = True
    matches = resolve_effective_matches(raw_matches, row)
    registry_npi = interpretation.target_npi
    if not registry_npi and not role_mismatch and _is_surgeon(row) and len(matches) == 1:
        registry_npi = matches[0].npi
    npi_data = get_npi_data(registry_npi)

    if role_mismatch and matches:
        return ValidationResult(
            status=ValidationStatus.MANUAL_REVIEW_REQUIRED,
            details="Only opposite-role dictionary matches were found; verify Provider vs Surgeon before applying.",
            matches=matches,
            npi_registry_name=_registry_full_name(npi_data),
            npi_registry_data=npi_data,
            needs_manual_review=True,
            effective_match=matches[0] if len(matches) == 1 else None,
        )
    if len(matches) > 1:
        return ValidationResult(
            status=ValidationStatus.MULTIPLE_MATCHES,
            details="Multiple dictionary matches require manual resolution.",
            matches=matches,
            npi_registry_name=_registry_full_name(npi_data),
            npi_registry_data=npi_data,
            needs_manual_review=True,
            effective_match=None,
        )
    if matches and _is_deactivated(matches[0].deactivation_status):
        return ValidationResult(
            status=ValidationStatus.DEACTIVATED_PROVIDER,
            details="Only dictionary match is deactivated.",
            matches=matches,
            npi_registry_name=_registry_full_name(npi_data),
            npi_registry_data=npi_data,
            needs_manual_review=True,
            effective_match=matches[0],
        )
    if matches:
        status = ValidationStatus.VALIDATED if interpretation.target_npi and interpretation.target_cbcode else (
            ValidationStatus.NPI_FOUND if interpretation.target_npi else ValidationStatus.CBCODE_FOUND
        )
        return ValidationResult(
            status=status,
            details="Dictionary match found.",
            matches=matches,
            npi_registry_name=_registry_full_name(npi_data),
            npi_registry_data=npi_data,
            needs_manual_review=False,
            effective_match=matches[0],
        )
    if interpretation.target_cbcode:
        return ValidationResult(
            status=ValidationStatus.CBCODE_NOT_FOUND,
            details="Target CBCode was not found in loaded dictionaries.",
            matches=[],
            npi_registry_name=_registry_full_name(npi_data),
            npi_registry_data=npi_data,
            needs_manual_review=True,
        )
    if interpretation.target_npi:
        return ValidationResult(
            status=ValidationStatus.NPI_FOUND if npi_data else ValidationStatus.NPI_NOT_FOUND,
            details="NPI Registry lookup completed.",
            matches=[],
            npi_registry_name=_registry_full_name(npi_data),
            npi_registry_data=npi_data,
            needs_manual_review=not bool(npi_data),
        )
    return ValidationResult(
        status=ValidationStatus.AMBIGUOUS_COMMENT,
        details="No target NPI, CBCode, or provider name could be validated.",
        matches=[],
        npi_registry_name=None,
        needs_manual_review=True,
    )
