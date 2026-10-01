"""
Lumen Authentication Handler - OAuth2 and session management.

Handles authentication flows, token generation, storage, and revocation
for Brightspace OAuth2 with security best practices.
"""

import logging
import secrets
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs
import hashlib

import requests

from .lumen_config import LumenConfig
from .lumen_exceptions import LumenAuthError


logger = logging.getLogger(__name__)


class LumenAuth:
    """
    Handle OAuth2 authentication with Brightspace/Lumen.
    
    Implements:
    - Authorization code flow with PKCE
    - Token generation and refresh
    - Secure state validation
    - Token revocation
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        config: Optional[LumenConfig] = None,
    ):
        """
        Initialize authentication handler.
        
        Args:
            base_url: Brightspace instance URL
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            redirect_uri: Registered callback URI
            config: LumenConfig instance
        """
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.config = config or LumenConfig()
        
        # PKCE parameters
        self._code_verifier: Optional[str] = None
        self._state: Optional[str] = None
        
        logger.info(f"Auth handler initialized for {self.base_url}")

    def generate_auth_url(self) -> Tuple[str, str, str]:
        """
        Generate OAuth2 authorization URL with PKCE.
        
        Returns:
            Tuple of (auth_url, state, code_verifier)
            Store state and code_verifier for later validation
        """
        # Generate PKCE parameters
        self._code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(self._code_verifier)
        
        # Generate state for CSRF protection
        self._state = self._generate_state()
        
        # Build authorization URL
        auth_endpoint = urljoin(self.base_url, "/core/oauth2/auth")
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.config.oauth_scopes,
            "state": self._state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        auth_url = f"{auth_endpoint}?{query_string}"
        
        logger.info("Authorization URL generated")
        return auth_url, self._state, self._code_verifier

    def exchange_code_for_token(
        self,
        authorization_code: str,
        state: str,
        code_verifier: str,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            authorization_code: Authorization code from redirect
            state: State parameter for validation
            code_verifier: PKCE code verifier
            
        Returns:
            Token response dict with access_token, refresh_token, expires_in
            
        Raises:
            LumenAuthError: If exchange fails or state mismatch
        """
        if state != self._state:
            logger.error("State mismatch - possible CSRF attack")
            raise LumenAuthError("State validation failed - possible CSRF attack")
        
        token_endpoint = urljoin(self.base_url, "/core/oauth2/token")
        payload = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }
        
        try:
            response = requests.post(
                token_endpoint,
                data=payload,
                timeout=self.config.request_timeout,
                headers={"User-Agent": f"Academic-OS/1.0 LumenAuth/{self.config.version}"},
            )
            response.raise_for_status()
            
            token_data = response.json()
            
            # Validate required fields
            required_fields = ["access_token", "expires_in"]
            if not all(field in token_data for field in required_fields):
                raise LumenAuthError(f"Missing required fields: {required_fields}")
            
            logger.info("Authorization code exchanged for tokens")
            return token_data
        
        except requests.exceptions.Timeout:
            logger.error("Token exchange timeout")
            raise LumenAuthError("Token exchange request timed out")
        except requests.exceptions.HTTPError as e:
            try:
                error_data = e.response.json()
            except Exception:
                error_data = {"error": e.response.text}
            
            logger.error(f"Token exchange failed: {error_data}")
            raise LumenAuthError(f"Token exchange failed: {error_data}")
        except Exception as e:
            logger.error(f"Token exchange error: {str(e)}")
            raise LumenAuthError(f"Token exchange error: {str(e)}")

    def validate_callback_uri(self, callback_uri: str) -> Tuple[str, str]:
        """
        Parse and validate OAuth2 callback URI.
        
        Args:
            callback_uri: Full redirect URI with code and state
            
        Returns:
            Tuple of (authorization_code, state)
            
        Raises:
            LumenAuthError: If parameters are missing
        """
        parsed = urlparse(callback_uri)
        params = parse_qs(parsed.query)
        
        # Check for errors
        if "error" in params:
            error = params["error"][0]
            description = params.get("error_description", [""])[0]
            logger.error(f"OAuth error: {error} - {description}")
            raise LumenAuthError(f"OAuth error: {error} - {description}")
        
        # Extract code and state
        if "code" not in params or "state" not in params:
            logger.error("Missing code or state in callback URI")
            raise LumenAuthError("Missing code or state in callback URI")
        
        code = params["code"][0]
        state = params["state"][0]
        
        logger.debug("Callback URI validated")
        return code, state

    def revoke_token(self, token: str) -> bool:
        """
        Revoke access token or refresh token.
        
        Args:
            token: Access or refresh token to revoke
            
        Returns:
            True if revocation successful
        """
        revoke_endpoint = urljoin(self.base_url, "/core/oauth2/revoke")
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "token": token,
        }
        
        try:
            response = requests.post(
                revoke_endpoint,
                data=payload,
                timeout=self.config.request_timeout,
            )
            response.raise_for_status()
            logger.info("Token revoked successfully")
            return True
        except Exception as e:
            logger.error(f"Token revocation failed: {str(e)}")
            return False

    def _generate_code_verifier(self) -> str:
        """
        Generate PKCE code verifier.
        
        Returns:
            URL-safe random string (43-128 chars)
        """
        return secrets.token_urlsafe(96)[:128]

    def _generate_code_challenge(self, verifier: str) -> str:
        """
        Generate PKCE code challenge from verifier.
        
        Args:
            verifier: Code verifier string
            
        Returns:
            URL-safe base64 encoded SHA256 hash
        """
        digest = hashlib.sha256(verifier.encode()).digest()
        # Base64 URL-safe encode
        import base64
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def _generate_state(self) -> str:
        """Generate CSRF protection state parameter."""
        return secrets.token_urlsafe(32)


class LumenAuthCallback:
    """
    Handle OAuth2 callback processing and validation.
    
    Validates state, exchanges code, and manages token storage.
    """

    def __init__(
        self,
        auth: LumenAuth,
        state: str,
        code_verifier: str,
    ):
        """
        Initialize callback handler.
        
        Args:
            auth: LumenAuth instance
            state: Original state parameter
            code_verifier: Original code verifier
        """
        self.auth = auth
        self.state = state
        self.code_verifier = code_verifier

    def handle_callback(self, callback_uri: str) -> Dict[str, Any]:
        """
        Process OAuth2 callback.
        
        Args:
            callback_uri: Full redirect URI from OAuth provider
            
        Returns:
            Token data dict
            
        Raises:
            LumenAuthError: If callback is invalid
        """
        # Parse and validate callback
        code, state = self.auth.validate_callback_uri(callback_uri)
        
        # Verify state
        if state != self.state:
            logger.error("State mismatch in callback")
            raise LumenAuthError("State validation failed")
        
        # Exchange code for token
        token_data = self.auth.exchange_code_for_token(
            authorization_code=code,
            state=state,
            code_verifier=self.code_verifier,
        )
        
        logger.info("OAuth callback processed successfully")
        return token_data
