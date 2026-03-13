"""Configuration for data sources module."""

from __future__ import annotations

import os
from dataclasses import dataclass

from word_store.db import resolve_database_dsn


@dataclass(slots=True)
class DataSourcesConfig:
    """Configuration for data source ingestion and retrieval."""

    database_dsn: str
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    extraction_model: str = "gpt-5-mini"
    extraction_max_tokens: int = 32768
    retrieval_model: str = "gpt-5-mini"
    retrieval_max_tokens: int = 32768
    retrieval_top_k: int = 20
    reranker_top_k: int = 15
    vision_model: str = "gpt-5-mini"
    vision_max_tokens: int = 16000
    vision_dpi_scale: float = 2.0
    extraction_max_workers: int = 8
    vision_max_workers: int = 4
    openai_base_url: str | None = None
    openai_oauth_token_url: str | None = None
    openai_oauth_client_id: str | None = None
    openai_oauth_client_secret: str | None = None
    openai_oauth_scope: str | None = None
    openai_skip_ssl_verify: bool = False

    def is_oauth_configured(self) -> bool:
        """Return True if all OAuth2 client credentials fields are set."""
        return bool(
            self.openai_oauth_token_url
            and self.openai_oauth_client_id
            and self.openai_oauth_client_secret
        )

    @classmethod
    def from_env(cls) -> DataSourcesConfig:
        """Build config from environment variables (and .env file if present).

        Authentication priority:
          1. OAuth2 (OPENAI_OAUTH_TOKEN_URL + CLIENT_ID + CLIENT_SECRET)
          2. Static API key (OPENAI_API_KEY)
        At least one must be configured.

        Model/token overrides (all optional):
          OPENAI_CHAT_MODEL           — sets extraction_model, retrieval_model, vision_model
          OPENAI_EMBEDDING_MODEL      — sets embedding_model
          OPENAI_MAX_COMPLETION_TOKENS — sets extraction_max_tokens, retrieval_max_tokens,
                                         vision_max_tokens
        """
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        dsn = resolve_database_dsn()
        api_key = os.environ.get("OPENAI_API_KEY", "")
        oauth_token_url = os.environ.get("OPENAI_OAUTH_TOKEN_URL", "") or None
        oauth_client_id = os.environ.get("OPENAI_OAUTH_CLIENT_ID", "") or None
        oauth_client_secret = os.environ.get("OPENAI_OAUTH_CLIENT_SECRET", "") or None
        oauth_scope = os.environ.get("OPENAI_OAUTH_SCOPE", "") or None
        base_url = os.environ.get("OPENAI_BASE_URL", "") or None
        skip_ssl = os.environ.get("OPENAI_SKIP_SSL_VERIFY", "").lower() in ("1", "true", "yes")

        is_oauth = bool(oauth_token_url and oauth_client_id and oauth_client_secret)
        if not api_key and not is_oauth:
            raise ValueError(
                "Authentication required: set OPENAI_API_KEY or "
                "OPENAI_OAUTH_TOKEN_URL + OPENAI_OAUTH_CLIENT_ID + OPENAI_OAUTH_CLIENT_SECRET"
            )

        # Model name overrides
        chat_model = os.environ.get("OPENAI_CHAT_MODEL", "") or None
        embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "") or None

        # Token limit override
        max_tokens_str = os.environ.get("OPENAI_MAX_COMPLETION_TOKENS", "")
        max_tokens = int(max_tokens_str) if max_tokens_str.strip().isdigit() else None

        kwargs: dict = dict(
            database_dsn=dsn,
            openai_api_key=api_key,
            openai_base_url=base_url,
            openai_oauth_token_url=oauth_token_url,
            openai_oauth_client_id=oauth_client_id,
            openai_oauth_client_secret=oauth_client_secret,
            openai_oauth_scope=oauth_scope,
            openai_skip_ssl_verify=skip_ssl,
        )
        if chat_model:
            kwargs["extraction_model"] = chat_model
            kwargs["retrieval_model"] = chat_model
            kwargs["vision_model"] = chat_model
        if embedding_model:
            kwargs["embedding_model"] = embedding_model
        if max_tokens is not None:
            kwargs["extraction_max_tokens"] = max_tokens
            kwargs["retrieval_max_tokens"] = max_tokens
            kwargs["vision_max_tokens"] = max_tokens

        return cls(**kwargs)
