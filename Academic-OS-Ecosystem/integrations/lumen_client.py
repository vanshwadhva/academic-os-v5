"""
Lumen LMS API Client - Main entry point for Brightspace integration.

Provides secure, production-grade access to BITS Digital Lumen (Brightspace) API
with automatic retry, rate limiting, logging, and error handling.
"""

import logging
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from urllib.parse import urljoin
import json

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from cryptography.fernet import Fernet

from .lumen_config import LumenConfig
from .lumen_exceptions import (
    LumenAuthError,
    LumenAPIError,
    LumenRateLimitError,
    LumenTokenExpiredError,
)


logger = logging.getLogger(__name__)


class LumenClient:
    """
    Production-grade Lumen/Brightspace API client.
    
    Handles:
    - Token refresh and session management
    - Secure credential storage
    - Request retry with exponential backoff
    - Rate limit handling
    - Structured error handling and logging
    - Request/response auditing
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        encryption_key: Optional[str] = None,
        config: Optional[LumenConfig] = None,
    ):
        """
        Initialize Lumen API client.
        
        Args:
            base_url: Brightspace instance URL (e.g., https://lumen.bits-pilani.ac.in)
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            encryption_key: Fernet encryption key for token storage
            config: LumenConfig instance (uses defaults if None)
        """
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.config = config or LumenConfig()
        
        # Token management
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._refresh_token: Optional[str] = None
        
        # Encryption for stored tokens
        self.cipher = Fernet(encryption_key) if encryption_key else None
        
        # HTTP session with retry strategy
        self.session = self._build_session()
        
        logger.info(f"Lumen client initialized for {self.base_url}")

    def _build_session(self) -> requests.Session:
        """Build requests session with retry strategy."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.config.max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            backoff_factor=self.config.backoff_factor,
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            "User-Agent": f"Academic-OS/1.0 LumenClient/{self.config.version}",
        })
        
        return session

    def set_access_token(
        self,
        access_token: str,
        expires_in: int,
        refresh_token: Optional[str] = None,
    ) -> None:
        """
        Set access token from OAuth2 response.
        
        Args:
            access_token: Bearer token
            expires_in: Token validity in seconds
            refresh_token: Optional refresh token for re-authentication
        """
        self._access_token = access_token
        self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        if refresh_token:
            self._refresh_token = refresh_token
        
        logger.debug("Access token set, expires at %s", self._token_expires_at)

    def set_encrypted_token(
        self,
        encrypted_token: str,
        expires_in: int,
        encrypted_refresh: Optional[str] = None,
    ) -> None:
        """
        Decrypt and set access token from encrypted storage.
        
        Args:
            encrypted_token: Encrypted access token
            expires_in: Token validity in seconds
            encrypted_refresh: Optional encrypted refresh token
        """
        if not self.cipher:
            raise LumenAuthError("Encryption key not configured")
        
        try:
            access_token = self.cipher.decrypt(encrypted_token.encode()).decode()
            refresh_token = None
            if encrypted_refresh:
                refresh_token = self.cipher.decrypt(encrypted_refresh.encode()).decode()
            
            self.set_access_token(access_token, expires_in, refresh_token)
        except Exception as e:
            logger.error("Failed to decrypt token: %s", str(e))
            raise LumenAuthError(f"Token decryption failed: {str(e)}")

    def get_encrypted_token(self) -> Tuple[str, Optional[str]]:
        """
        Get encrypted versions of current tokens.
        
        Returns:
            Tuple of (encrypted_access_token, encrypted_refresh_token)
            
        Raises:
            LumenAuthError: If no token is set or encryption is not configured
        """
        if not self._access_token or not self.cipher:
            raise LumenAuthError("No token set or encryption not configured")
        
        encrypted_access = self.cipher.encrypt(self._access_token.encode()).decode()
        encrypted_refresh = None
        if self._refresh_token:
            encrypted_refresh = self.cipher.encrypt(self._refresh_token.encode()).decode()
        
        return encrypted_access, encrypted_refresh

    def is_token_expired(self) -> bool:
        """Check if current token has expired."""
        if not self._token_expires_at:
            return True
        
        # Refresh if within 5 minutes of expiry
        return datetime.utcnow() >= (self._token_expires_at - timedelta(minutes=5))

    def refresh_token_if_needed(self) -> bool:
        """
        Refresh access token if expired.
        
        Returns:
            True if token was refreshed or already valid, False if refresh failed
        """
        if not self.is_token_expired():
            return True
        
        if not self._refresh_token:
            logger.error("Token expired but no refresh token available")
            raise LumenTokenExpiredError("Token expired and refresh token unavailable")
        
        try:
            return self._refresh_access_token()
        except Exception as e:
            logger.error("Token refresh failed: %s", str(e))
            raise LumenTokenExpiredError(f"Token refresh failed: {str(e)}")

    def _refresh_access_token(self) -> bool:
        """Internal method to refresh token using refresh_token grant."""
        url = urljoin(self.base_url, "/core/oauth2/token")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        
        try:
            response = self.session.post(
                url,
                data=payload,
                timeout=self.config.request_timeout,
            )
            response.raise_for_status()
            
            data = response.json()
            self.set_access_token(
                access_token=data["access_token"],
                expires_in=data.get("expires_in", 3600),
                refresh_token=data.get("refresh_token", self._refresh_token),
            )
            logger.info("Token refreshed successfully")
            return True
        except Exception as e:
            logger.error("Token refresh failed: %s", str(e))
            raise

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authorization."""
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        return headers

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        raw_url: bool = False,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Lumen API with automatic token refresh.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path or full URL if raw_url=True
            params: Query parameters
            json_data: JSON request body
            raw_url: If True, endpoint is treated as full URL
            
        Returns:
            Parsed JSON response
            
        Raises:
            LumenTokenExpiredError: If token cannot be refreshed
            LumenRateLimitError: If rate limited
            LumenAPIError: On API errors
        """
        # Ensure token is fresh
        self.refresh_token_if_needed()
        
        # Build URL
        url = endpoint if raw_url else urljoin(self.base_url, endpoint)
        
        # Prepare request
        headers = self._get_headers()
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
                timeout=self.config.request_timeout,
            )
            
            # Log request for audit
            self._log_request(method, url, response.status_code)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited, retry after {retry_after}s")
                time.sleep(retry_after)
                return self.request(method, endpoint, params, json_data, raw_url)
            
            response.raise_for_status()
            return response.json() if response.text else {}
        
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout: {method} {url}")
            raise LumenAPIError(f"Request timeout for {endpoint}")
        except requests.exceptions.HTTPError as e:
            self._handle_http_error(e, method, url)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {method} {url}: {str(e)}")
            raise LumenAPIError(f"Request failed: {str(e)}")

    def _handle_http_error(
        self,
        error: requests.exceptions.HTTPError,
        method: str,
        url: str,
    ) -> None:
        """Handle HTTP errors with proper exception mapping."""
        status_code = error.response.status_code
        
        try:
            error_data = error.response.json()
        except Exception:
            error_data = {"error": error.response.text}
        
        if status_code == 401:
            logger.error(f"Authentication failed: {error_data}")
            raise LumenAuthError(f"Authentication failed: {error_data}")
        elif status_code == 403:
            logger.error(f"Access forbidden: {error_data}")
            raise LumenAuthError(f"Access forbidden: {error_data}")
        elif status_code == 404:
            logger.warning(f"Resource not found: {url}")
            raise LumenAPIError(f"Resource not found: {url}")
        else:
            logger.error(f"API error {status_code}: {error_data}")
            raise LumenAPIError(f"API error {status_code}: {error_data}")

    def _log_request(self, method: str, url: str, status: int) -> None:
        """Log request for audit trail."""
        # Mask sensitive data
        masked_url = url.replace(self.client_secret, "***")
        logger.debug(f"{method} {masked_url} -> {status}")

    def get_paginated(
        self,
        endpoint: str,
        page_size: int = 100,
        max_pages: Optional[int] = None,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch paginated endpoint and return all results.
        
        Args:
            endpoint: API endpoint
            page_size: Items per page
            max_pages: Maximum pages to fetch (None = all)
            
        Returns:
            List of all items from all pages
        """
        all_items: List[Dict[str, Any]] = []
        page = 0
        bookmark = None
        
        while True:
            params: Dict[str, Any] = {**(query_params or {}), "pageSize": page_size}
            if bookmark:
                params["bookmark"] = bookmark
            
            try:
                response = self.request("GET", endpoint, params=params)
                
                if isinstance(response, list):
                    items = response
                    paging_info = {}
                else:
                    items = (
                        response.get("Items")
                        or response.get("Modules")
                        or response.get("Objects")
                        or response.get("Data")
                        or []
                    )
                    paging_info = response.get("PagingInfo", {})
                all_items.extend(items)
                
                # Check for pagination
                bookmark = paging_info.get("Bookmark")
                
                page += 1
                if max_pages and page >= max_pages:
                    break
                
                if not bookmark:
                    break
                
                # Respect rate limiting
                time.sleep(self.config.request_delay)
            
            except Exception as e:
                logger.error(f"Pagination failed at page {page}: {str(e)}")
                raise
        
        logger.info(f"Fetched {len(all_items)} items from {endpoint}")
        return all_items

    def close(self) -> None:
        """Close session and cleanup."""
        self.session.close()
        logger.info("Lumen client session closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
