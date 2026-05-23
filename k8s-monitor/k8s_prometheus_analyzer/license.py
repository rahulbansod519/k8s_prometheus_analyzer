"""Offline license key validation using asymmetric cryptography (RS256 JWT)."""

from __future__ import annotations

import logging
import os

import jwt

from .exceptions import LicenseError, LicenseExpiredError, LicenseSignatureError

logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAy+JPfLeidJLB/QLdl4s+
zf/7giLFyKOQ/CQUFse7B14jbkFS7dpRGFW/t27+IUbJVfA1e2yBldbnznHRzoFo
8CIgfYz5HXZv4OhhpUPm9YsuO+A024r3xmlDkeO1zMFrGWrJY+OwEEE2xAO8BPmJ
PQor1kP4V82jjrb6lHQeqwbrS4z2OJeWgM0fBgdbjdavRcK02nqrpujAIy3GTBFG
Ks7+OIjeu7fAVCTBQBqLolIdRVLn4N1CseGO2V/MrBHO0HWTViMfEZsv0xckWAiB
/yR2o3nuKr8GDSBuw6/qx1V2rxfS7Azpf5C52Iwa81L58ShSf2rg6BP/A8/2L3/F
HwIDAQAB
-----END PUBLIC KEY-----"""


def get_public_key() -> str:
    """Retrieve the RSA public key for verification.

    Can be overridden via the environment variable K8S_ANALYZER_PUBLIC_KEY.
    """
    return os.environ.get("K8S_ANALYZER_PUBLIC_KEY", DEFAULT_PUBLIC_KEY)


def verify_license(license_token: str) -> dict:
    """Decode and verify an RS256 JWT license token.

    Args:
        license_token: The string representation of the signed JWT.

    Returns:
        dict: The verified license claims/payload.

    Raises:
        LicenseExpiredError: If the token's expiration date is in the past.
        LicenseSignatureError: If the token's signature check fails.
        LicenseError: If the token format is invalid or missing required claims.
    """
    public_key = get_public_key()
    try:
        # jwt.decode automatically verifies expiration (exp) and signature
        payload = jwt.decode(
            license_token.strip(),
            public_key,
            algorithms=["RS256"],
            options={"require": ["exp", "limits"]},
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise LicenseExpiredError("The license key has expired.") from e
    except jwt.InvalidSignatureError as e:
        raise LicenseSignatureError("The license signature check failed.") from e
    except jwt.InvalidTokenError as e:
        raise LicenseError(f"Invalid license key format: {e}") from e
