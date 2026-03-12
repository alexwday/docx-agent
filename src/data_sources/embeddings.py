"""OpenAI text-embedding-3-large wrapper with batching and retry."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import openai

from data_sources.auth import build_openai_client

if TYPE_CHECKING:
    from data_sources.config import DataSourcesConfig

logger = logging.getLogger(__name__)

__all__ = ["embed_texts"]

# OpenAI embeddings API accepts up to 2048 inputs per batch, but we keep
# batches small to avoid timeouts on large texts.
_BATCH_SIZE = 50
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0
_RETRYABLE_OPENAI_ERRORS = tuple(
    exc
    for exc in (
        getattr(openai, "RateLimitError", None),
        getattr(openai, "APITimeoutError", None),
        getattr(openai, "APIConnectionError", None),
        getattr(openai, "InternalServerError", None),
    )
    if exc is not None
)


def embed_texts(
    texts: list[str],
    *,
    config: DataSourcesConfig,
    model: str = "text-embedding-3-large",
    dimensions: int = 3072,
) -> list[list[float]]:
    """Embed a list of texts, returning one embedding vector per text.

    Handles batching and retries internally.
    """
    if not texts:
        return []

    client = build_openai_client(config)
    all_embeddings: list[list[float]] = [[] for _ in texts]

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start : batch_start + _BATCH_SIZE]
        # Replace empty strings with a placeholder (API rejects empty input)
        batch_clean = [t if t.strip() else "[empty]" for t in batch]

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = client.embeddings.create(
                    input=batch_clean,
                    model=model,
                    dimensions=dimensions,
                )
                for item in response.data:
                    all_embeddings[batch_start + item.index] = item.embedding
                logger.debug(
                    "Embedded batch %d-%d (%d items)",
                    batch_start,
                    batch_start + len(batch) - 1,
                    len(batch),
                )
                break
            except _RETRYABLE_OPENAI_ERRORS as exc:
                if attempt == _MAX_RETRIES:
                    raise
                wait = _RETRY_DELAY * attempt
                logger.warning(
                    "Embedding retry %d/%d after %s: %s",
                    attempt,
                    _MAX_RETRIES,
                    wait,
                    exc,
                    exc_info=True,
                )
                time.sleep(wait)

    return all_embeddings
