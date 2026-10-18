"""
Shared test setup.

Environment variables must be set before ``backend.main`` is imported, because
it reads configuration at import time. Everything is redirected to a temp
directory so the tests never touch the real database or credential store.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="academic-os-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["LUMEN_CREDENTIALS_PATH"] = f"{_TMP}/lumen_credentials.bin"
os.environ.setdefault("LUMEN_BASE_URL", "https://lumen.test.example")
os.environ.setdefault("LUMEN_CLIENT_ID", "test-client-id")
os.environ.setdefault("LUMEN_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("CORS_ORIGINS", "")

from cryptography.fernet import Fernet  # noqa: E402

os.environ["LUMEN_CREDENTIALS_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
