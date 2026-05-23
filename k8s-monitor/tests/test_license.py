"""Unit tests for offline license key validation."""

from __future__ import annotations

import time
from unittest.mock import patch

import jwt
import pytest

from k8s_prometheus_analyzer.exceptions import (
    LicenseError,
    LicenseExpiredError,
    LicenseSignatureError,
)
from k8s_prometheus_analyzer.license import verify_license

# Hardcoded test keys (matching pairs) for cryptographic test validity
TEST_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAy+JPfLeidJLB/QLdl4s+zf/7giLFyKOQ/CQUFse7B14jbkFS
7dpRGFW/t27+IUbJVfA1e2yBldbnznHRzoFo8CIgfYz5HXZv4OhhpUPm9YsuO+A0
24r3xmlDkeO1zMFrGWrJY+OwEEE2xAO8BPmJPQor1kP4V82jjrb6lHQeqwbrS4z2
OJeWgM0fBgdbjdavRcK02nqrpujAIy3GTBFGKs7+OIjeu7fAVCTBQBqLolIdRVLn
4N1CseGO2V/MrBHO0HWTViMfEZsv0xckWAiB/yR2o3nuKr8GDSBuw6/qx1V2rxfS
7Azpf5C52Iwa81L58ShSf2rg6BP/A8/2L3/FHwIDAQABAoIBAC4CgMiW0kD3W3Ki
4mnQARjQ0yuveC3Kh6324FextAm6G0nG0RWfBlz1AOI+2Hee91F+9zrGpkmvqTkj
42J0Pr+uG+HpXdBhyWaaWmrGs4im44ScmKEQr9ClMZvrJLwzy9z9BbyWhcVtShQa
+aOvwmI1eOYOCa2a2PWcYlj9CWyzqAnXY0S6aPXdzKmxq/e0ytwrZvQ2Ug1CL8Hh
wTUI11X8N7sVvGJdBH8pACewb26jwU2v/bu8oFwmr6Qk9udLjwcriCYePEGYLC3Z
lA7lW98BW9rIGQ1reQUFdwypS6nG2ag1CPMTIaCetRn0cBnardTSSaNIJZsHRTiu
ugprId0CgYEA+MYFmM0MHrGSFViiHU/54d7Z1MMdwz68Bk3GF8OvmcMRfDAGDUPl
G0SsqWXslmEbqXLPNbi+jIQD0LF/rjY737uXrbjgILkg8vsNGXB0rxc52LqYB49U
2CQ/k/6qCfTjHMTU3OcxqbHXjE0P0JfnWzV603XgFXcVPf3uF6x92dUCgYEA0c54
/MdaCYi3Lnx7QhPs8UAzbyleaMGOp5IhkVo5hrDPzOjEDMcRWeP4XnahbZko0D9w
QjY0KBJGH4ZrJhA4b+dyBtrRCcFtO8L8f9tx4kDSuS/pwOpJETF1KWwSXIhIl9Ap
/3WeSAniucjE9riITH7MQY1tdPfmQ+kAjiHYiSMCgYEA7XsLqLxFT5+vlpUP3O+V
2VsFkyfX56ShlVr1OYZiwWQH8wddH5iqwwch1GwqF7wHzhB9YglETZtQkQ6AlmvL
aF8KApqzykkv/QRPkvNZUDPZ0tz9eGoJUnP4BW1cITkW/UWg9mf1bssIuzRtXnFE
ODurTuX9zj/plU4s1YiicykCgYArflQSgvklVNQ0rNWYgyzxbk+7UaYirU13a5HN
4hhe1bSeU/qgc3wjWGEapBke8UtGsIADGd2CGRe0XVdFEsPAXwiCZ0ZCcXjFlMxn
bQSU1L9aaJZaybbP+6LALYk46X+zCRJLxQRFBtebkAVU6DhJM1gAluMEBogTt+/H
hziuZQKBgQDq5S4jEIFlc0Gg6GISQ9cCTp8PFsjRu4TboYhReyCyeRdXn0hU+6KS
tz1U+tdcHsceONwlVUzkSs50CfZ4ecRjpinwiEGiIvWN0yTcQmPhekjteEfDRxcG
zR8YJG4KcaYr4b/HN9ChcGL3lXWJREGKCgfR6C4t29cJGWcIJehT2g==
-----END RSA PRIVATE KEY-----"""

TEST_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAy+JPfLeidJLB/QLdl4s+
zf/7giLFyKOQ/CQUFse7B14jbkFS7dpRGFW/t27+IUbJVfA1e2yBldbnznHRzoFo
8CIgfYz5HXZv4OhhpUPm9YsuO+A024r3xmlDkeO1zMFrGWrJY+OwEEE2xAO8BPmJ
PQor1kP4V82jjrb6lHQeqwbrS4z2OJeWgM0fBgdbjdavRcK02nqrpujAIy3GTBFG
Ks7+OIjeu7fAVCTBQBqLolIdRVLn4N1CseGO2V/MrBHO0HWTViMfEZsv0xckWAiB
/yR2o3nuKr8GDSBuw6/qx1V2rxfS7Azpf5C52Iwa81L58ShSf2rg6BP/A8/2L3/F
HwIDAQAB
-----END PUBLIC KEY-----"""


@pytest.fixture(autouse=True)
def mock_public_key():
    """Ensure the validator uses our test public key instead of the default production one."""
    with patch(
        "k8s_prometheus_analyzer.license.get_public_key", return_value=TEST_PUBLIC_KEY
    ):
        yield


def test_verify_license_valid():
    """Verify that a valid token signed with the private key decodes successfully."""
    payload = {
        "sub": "test-client",
        "exp": int(time.time()) + 3600,
        "limits": {"nodes": 50},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")
    result = verify_license(token)
    assert result["sub"] == "test-client"
    assert result["limits"]["nodes"] == 50


def test_verify_license_expired():
    """Verify that an expired token raises LicenseExpiredError."""
    payload = {
        "sub": "test-client",
        "exp": int(time.time()) - 3600,
        "limits": {"nodes": 50},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")
    with pytest.raises(LicenseExpiredError):
        verify_license(token)


def test_verify_license_invalid_signature():
    """Verify that a tampered signature raises LicenseSignatureError."""
    payload = {
        "sub": "test-client",
        "exp": int(time.time()) + 3600,
        "limits": {"nodes": 50},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")
    # Tamper with the token string signature (last characters)
    tampered_token = token[:-4] + "aaaa"
    with pytest.raises(LicenseSignatureError):
        verify_license(tampered_token)


def test_verify_license_malformed():
    """Verify that a non-JWT string raises LicenseError."""
    with pytest.raises(LicenseError):
        verify_license("not-a-valid-jwt-token")


def test_verify_license_missing_claims():
    """Verify that a JWT missing required claims raises LicenseError."""
    payload = {
        "sub": "test-client",
        # Missing 'exp' and 'limits'
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")
    with pytest.raises(LicenseError):
        verify_license(token)
