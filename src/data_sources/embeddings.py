"""OpenAI text-embedding-3-large wrapper with batching, parallelism, and retry."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

import openai

from data_sources.auth import build_openai_client

if TYPE_CHECKING:
    from data_sources.config import DataSourcesConfig

logger = logging.getLogger(__name__)

__all__ = ["embed_texts"]

# OpenAI embeddings API accepts up to 2048 inputs per batch.
_BATCH_SIZE = 200
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0
_EMBED_WORKERS = 8
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

    Splits into batches of _BATCH_SIZE and submits all batches concurrently
    via ThreadPoolExecutor. Handles retries per batch internally.
    """
    if not texts:
        return []

    client = build_openai_client(config)
    all_embeddings: list[list[float]] = [[] for _ in texts]

    batches = [
        (start, texts[start : start + _BATCH_SIZE])
        for start in range(0, len(texts), _BATCH_SIZE)
    ]

    if len(batches) > 1:
        logger.info("Embedding %d texts in %d batches (%d workers)", len(texts), len(batches), _EMBED_WORKERS)

    def _embed_batch(batch_start: int, batch: list[str]) -> tuple[int, list[tuple[int, list[float]]]]:
        batch_clean = [t if t.strip() else "[empty]" for t in batch]
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = client.embeddings.create(
                    input=batch_clean,
                    model=model,
                    dimensions=dimensions,
                )
                logger.debug(
                    "Embedded batch %d-%d (%d items)",
                    batch_start,
                    batch_start + len(batch) - 1,
                    len(batch),
                )
                return batch_start, [(item.index, item.embedding) for item in response.data]
            except _RETRYABLE_OPENAI_ERRORS as exc:
                if attempt == _MAX_RETRIES:
                    raise
                wait = _RETRY_DELAY * attempt
                logger.warning(
                    "Embedding retry %d/%d after %.1fs: %s",
                    attempt,
                    _MAX_RETRIES,
                    wait,
                    exc,
                    exc_info=True,
                )
                time.sleep(wait)
        raise RuntimeError("Exhausted retries")  # unreachable

    with ThreadPoolExecutor(max_workers=_EMBED_WORKERS) as pool:
        futures = {pool.submit(_embed_batch, start, batch): start for start, batch in batches}
        for future in as_completed(futures):
            batch_start, results = future.result()
            for idx, embedding in results:
                all_embeddings[batch_start + idx] = embedding

    return all_embeddings
