"""JWT, password hashing, and Fernet field-level encryption primitives."""
import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_value,
    decode_token,
    encrypt_value,
    hash_password,
    revoke_refresh_token,
    verify_password,
)


def test_password_hash_round_trip():
    hashed = hash_password("CorrectHorseBatteryStaple")
    assert hashed != "CorrectHorseBatteryStaple"
    assert verify_password("CorrectHorseBatteryStaple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_round_trip():
    token = create_access_token("user-123", "SalesRep", "org-456")
    claims = decode_token(token, "access")
    assert claims["sub"] == "user-123"
    assert claims["role"] == "SalesRep"
    assert claims["org_id"] == "org-456"
    assert claims["type"] == "access"


def test_access_token_rejects_tampered_signature():
    token = create_access_token("user-123", "SalesRep", "org-456")
    tampered = token[:-4] + "abcd"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tampered, "access")


def test_decode_rejects_wrong_token_type():
    token = create_access_token("user-123", "SalesRep", "org-456")
    with pytest.raises(jwt.InvalidTokenError, match="expected a refresh token"):
        decode_token(token, "refresh")


def test_refresh_token_allowlist_round_trip(fake_redis):
    token = create_refresh_token("user-789")
    claims = decode_token(token, "refresh")
    assert claims["sub"] == "user-789"
    assert claims["type"] == "refresh"


def test_revoked_refresh_token_fails_decode(fake_redis):
    token = create_refresh_token("user-789")
    revoke_refresh_token(token)
    with pytest.raises(jwt.InvalidTokenError, match="revoked or rotated"):
        decode_token(token, "refresh")


def test_fernet_encrypt_decrypt_round_trip():
    ciphertext = encrypt_value("18-digit-bank-account-number")
    assert ciphertext != "18-digit-bank-account-number"
    assert decrypt_value(ciphertext) == "18-digit-bank-account-number"


def test_encrypted_string_column_stores_ciphertext_not_plaintext(db_session):
    """End-to-end check through the ORM: the raw column value on disk is
    never the plaintext, but reading it back through the model decrypts it.
    """
    from sqlalchemy import text

    from tests.conftest import make_organization

    org = make_organization(db_session, legal_name="Encrypted Bank Test Co")
    org.bank_account_number = "000111222333444"
    db_session.commit()

    raw = db_session.execute(
        text("SELECT bank_account_number FROM organizations WHERE id = :id"),
        {"id": org.id},
    ).scalar_one()
    assert raw != "000111222333444"

    db_session.expire(org)
    assert org.bank_account_number == "000111222333444"
