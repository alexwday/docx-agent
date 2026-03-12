"""Runtime configuration for the DOCX engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class EngineConfig:
    """Configuration for file safety and operation bounds."""

    allowed_roots: list[Path] = field(default_factory=list)
    max_file_size_bytes: int = 50 * 1024 * 1024
    contract_version: str = "v1"

    def normalized_allowed_roots(self) -> list[Path]:
        roots = self.allowed_roots or [Path.cwd()]
        return [root.expanduser().resolve() for root in roots]
