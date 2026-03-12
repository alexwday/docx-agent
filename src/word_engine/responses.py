"""Structured response helpers."""

from __future__ import annotations

from typing import Any

from .errors import ErrorCode


def ok(contract_version: str, **payload: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"status": "ok", "contract_version": contract_version}
    data.update(payload)
    return data


def error(
    contract_version: str,
    error_code: ErrorCode,
    message: str,
    **payload: Any,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "status": "error",
        "contract_version": contract_version,
        "error_code": error_code.value,
        "message": message,
    }
    data.update(payload)
    return data
