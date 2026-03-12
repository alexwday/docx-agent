from __future__ import annotations

from pathlib import Path

import pytest

from word_engine import EngineConfig, WordDocumentService


@pytest.fixture
def make_service():
    def _make(root: Path) -> WordDocumentService:
        return WordDocumentService(config=EngineConfig(allowed_roots=[root]))

    return _make
