#!/usr/bin/env python3
"""
Grant the Firebase custom admin claim to the single dashboard admin account.

Usage:
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
  python scripts/create_admin.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ADMIN_EMAIL = os.getenv(
    "ADMIN_DASHBOARD_EMAIL",
    "2025em1300265@bitspilani-digital.edu.in",
).strip().lower()


def _load_firebase_admin():
    try:
        import firebase_admin
        from firebase_admin import auth, credentials
    except ImportError as exc:
        raise RuntimeError(
            "firebase-admin is required. Install it with `pip install firebase-admin`."
        ) from exc
    return firebase_admin, auth, credentials


def initialise_firebase(service_account: str | None = None) -> None:
    firebase_admin, _auth, credentials = _load_firebase_admin()
    if firebase_admin._apps:
        return

    service_account = service_account or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if service_account:
        service_account_path = Path(service_account).expanduser()
        if not service_account_path.exists():
            raise FileNotFoundError(f"Service account file not found: {service_account_path}")
        firebase_admin.initialize_app(credentials.Certificate(str(service_account_path)))
        return

    firebase_admin.initialize_app()


def grant_admin_claim(email: str, service_account: str | None = None) -> None:
    _firebase_admin, auth, _credentials = _load_firebase_admin()
    initialise_firebase(service_account)

    user = auth.get_user_by_email(email)
    existing_claims = user.custom_claims or {}
    updated_claims = {**existing_claims, "admin": True}
    auth.set_custom_user_claims(user.uid, updated_claims)

    print(f"Admin claim granted")
    print(f"uid={user.uid}")
    print(f"email={email}")
    print("Note: the user must sign out and sign in again to receive the updated token.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create/update the Academic OS admin user claim.")
    parser.add_argument("--email", default=ADMIN_EMAIL, help="Admin email to allow")
    parser.add_argument(
        "--service-account",
        default=None,
        help="Path to a Firebase service account JSON file",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    if email != ADMIN_EMAIL:
        print(
            f"Refusing to grant admin to {email}. "
            f"Only {ADMIN_EMAIL} is allowed by this deployment.",
            file=sys.stderr,
        )
        return 2

    try:
        grant_admin_claim(email, args.service_account)
    except Exception as exc:
        print(f"Failed to create admin claim: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
