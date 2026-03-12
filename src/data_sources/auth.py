"""OpenAI client factory with OAuth2, custom base URL, and RBC SSL support.

Priority order for authentication:
  1. OAuth2 client credentials (if OPENAI_OAUTH_TOKEN_URL + credentials set)
  2. Static OPENAI_API_KEY

SSL:
  - rbc_security.enable_certs() is called once on first use (optional, graceful fallback)
  - After that, certifi.where() returns the RBC CA bundle and httpx picks it up

Usage:
    from data_sources.auth import build_openai_client
    client = build_openai_client(config)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openai as _openai
    from data_sources.config import DataSourcesConfig

logger = logging.getLogger(__name__)

# ── SSL setup (run once) ──────────────────────────────────────────────────────

_ssl_lock = threading.Lock()
_ssl_initialized = False


def setup_rbc_ssl() -> None:
    """Call rbc_security.enable_certs() once per process, if available.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _ssl_initialized
    if _ssl_initialized:
        return
    with _ssl_lock:
        if _ssl_initialized:
            return
        try:
            import rbc_security  # type: ignore[import]
            rbc_security.enable_certs()
            logger.info("rbc_security: SSL certificates enabled")
        except ImportError:
            logger.debug("rbc_security not available — using system certificate store")
        except Exception as exc:
            logger.warning("rbc_security.enable_certs() failed (%s) — using system certificate store", exc)
        _ssl_initialized = True


# ── OAuth2 token manager ──────────────────────────────────────────────────────

class OAuthManager:
    """Thread-safe OAuth2 client credentials token manager with auto-refresh.

    Mirrors the cc-launcher OAuthManager:
      - Uses grant_type=client_credentials
      - Tries HTTPBasicAuth first; falls back to body parameters if server returns 400
      - Caches the token and refreshes when within refresh_buffer_seconds of expiry
    """

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
        refresh_buffer_seconds: int = 300,
        verify_ssl: bool = True,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._refresh_buffer = refresh_buffer_seconds
        self._verify_ssl = verify_ssl

        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid access token, fetching/refreshing as needed."""
        with self._lock:
            if self._access_token is None or time.time() >= self._expires_at - self._refresh_buffer:
                self._fetch_token()
            assert self._access_token is not None  # _fetch_token raises on failure
            return self._access_token

    def _fetch_token(self) -> None:
        try:
            import requests
            from requests.auth import HTTPBasicAuth
        except ImportError as exc:
            raise ImportError(
                "OAuth2 authentication requires requests: pip install requests"
            ) from exc

        data: dict[str, str] = {"grant_type": "client_credentials"}
        if self._scope:
            data["scope"] = self._scope

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        # Try HTTPBasicAuth first (preferred)
        response = requests.post(
            self._token_url,
            data=data,
            auth=HTTPBasicAuth(self._client_id, self._client_secret),
            headers=headers,
            timeout=30,
            verify=self._verify_ssl,
        )

        # Some servers reject Basic Auth and expect credentials in the body
        if response.status_code == 400:
            logger.debug("OAuth: Basic Auth returned 400, retrying with body parameters")
            data["client_id"] = self._client_id
            data["client_secret"] = self._client_secret
            response = requests.post(
                self._token_url,
                data=data,
                headers=headers,
                timeout=30,
                verify=self._verify_ssl,
            )

        response.raise_for_status()
        token_data = response.json()

        self._access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        self._expires_at = time.time() + expires_in
        logger.debug("OAuth: token fetched, expires in %ds", expires_in)


# ── Module-level OAuth manager cache ─────────────────────────────────────────

_oauth_managers: dict[str, OAuthManager] = {}
_oauth_cache_lock = threading.Lock()


def _get_oauth_manager(config: DataSourcesConfig) -> OAuthManager:
    """Return the cached OAuthManager for this config, creating it if needed."""
    key = config.openai_oauth_token_url or ""
    with _oauth_cache_lock:
        if key not in _oauth_managers:
            _oauth_managers[key] = OAuthManager(
                token_url=config.openai_oauth_token_url,  # type: ignore[arg-type]
                client_id=config.openai_oauth_client_id,  # type: ignore[arg-type]
                client_secret=config.openai_oauth_client_secret,  # type: ignore[arg-type]
                scope=config.openai_oauth_scope,
                verify_ssl=not config.openai_skip_ssl_verify,
            )
    return _oauth_managers[key]


# ── httpx client with RBC SSL ─────────────────────────────────────────────────

def _build_http_client(verify_ssl: bool = True):  # type: ignore[return]
    """Build an httpx.Client using certifi's CA bundle (patched by rbc_security)."""
    try:
        import certifi
        import httpx
        verify = certifi.where() if verify_ssl else False
        return httpx.Client(verify=verify)
    except ImportError:
        return None  # OpenAI SDK will use its own default httpx client


# ── Public factory ────────────────────────────────────────────────────────────

def build_openai_client(config: DataSourcesConfig) -> _openai.OpenAI:
    """Create a fully configured OpenAI client.

    - Calls rbc_security.enable_certs() on first use (idempotent)
    - Fetches/refreshes OAuth2 token if configured, else uses OPENAI_API_KEY
    - Applies custom base URL if configured
    - Passes a certifi-backed httpx.Client for RBC SSL certificate trust
    """
    import openai

    setup_rbc_ssl()

    # Resolve auth token
    if config.is_oauth_configured():
        try:
            api_key = _get_oauth_manager(config).get_token()
        except Exception as exc:
            logger.error("OAuth token fetch failed: %s — falling back to OPENAI_API_KEY", exc, exc_info=True)
            api_key = config.openai_api_key
    else:
        api_key = config.openai_api_key

    if not api_key:
        raise ValueError(
            "No API key available: OPENAI_API_KEY is empty and OAuth either is not configured "
            "or failed to fetch a token."
        )

    kwargs: dict = {"api_key": api_key}

    if config.openai_base_url:
        kwargs["base_url"] = config.openai_base_url

    http_client = _build_http_client(verify_ssl=not config.openai_skip_ssl_verify)
    if http_client is not None:
        kwargs["http_client"] = http_client

    logger.debug(
        "OpenAI client: base_url=%s auth=%s ssl_verify=%s",
        config.openai_base_url or "(default)",
        "oauth" if config.is_oauth_configured() else "api_key",
        not config.openai_skip_ssl_verify,
    )
    return openai.OpenAI(**kwargs)
