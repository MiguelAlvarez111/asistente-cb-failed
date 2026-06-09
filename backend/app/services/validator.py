from backend.app.schemas.ai import AIAction, AIInterpretation
from backend.app.schemas.results import ValidationResult, ValidationStatus
from typing import Any

from backend.app.services.dictionary_loader import DictionaryIndex, resolve_effective_matches
from backend.app.services.npi_registry import get_npi_data


def _is_deactivated(value: str | None) -> bool:
    return bool(value and value.strip().upper() not in {"", "N", "NO", "0", "FALSE"})


def _lookup_matches(interpretation: AIInterpretation, index: DictionaryIndex):
    if interpretation.action == AIAction.CHANGE_TICKET:
        if interpretation.target_cbcode:
            return index.lookup(cbcode=interpretation.target_cbcode)
        if interpretation.target_npi:
            return index.lookup(npi=interpretation.target_npi)
        if interpretation.target_provider_name:
            return index.lookup(provider_name=interpretation.target_provider_name)
        return []
    return index.lookup(
        npi=interpretation.target_npi,
        cbcode=interpretation.target_cbcode,
        provider_name=interpretation.target_provider_name,
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

    matches = resolve_effective_matches(_lookup_matches(interpretation, index), row)
    npi_data = get_npi_data(interpretation.target_npi)

    if len(matches) > 1:
        return ValidationResult(
            status=ValidationStatus.MULTIPLE_MATCHES,
            details="Multiple dictionary matches require manual resolution.",
            matches=matches,
            npi_registry_name=npi_data["full_name"] if npi_data else None,
            needs_manual_review=True,
            effective_match=None,
        )
    if matches and _is_deactivated(matches[0].deactivation_status):
        return ValidationResult(
            status=ValidationStatus.DEACTIVATED_PROVIDER,
            details="Only dictionary match is deactivated.",
            matches=matches,
            npi_registry_name=npi_data["full_name"] if npi_data else None,
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
            npi_registry_name=npi_data["full_name"] if npi_data else None,
            needs_manual_review=False,
            effective_match=matches[0],
        )
    if interpretation.target_cbcode:
        return ValidationResult(
            status=ValidationStatus.CBCODE_NOT_FOUND,
            details="Target CBCode was not found in loaded dictionaries.",
            matches=[],
            npi_registry_name=npi_data["full_name"] if npi_data else None,
            needs_manual_review=True,
        )
    if interpretation.target_npi:
        return ValidationResult(
            status=ValidationStatus.NPI_FOUND if npi_data else ValidationStatus.NPI_NOT_FOUND,
            details="NPI Registry lookup completed.",
            matches=[],
            npi_registry_name=npi_data["full_name"] if npi_data else None,
            needs_manual_review=not bool(npi_data),
        )
    return ValidationResult(
        status=ValidationStatus.AMBIGUOUS_COMMENT,
        details="No target NPI, CBCode, or provider name could be validated.",
        matches=[],
        npi_registry_name=None,
        needs_manual_review=True,
    )
