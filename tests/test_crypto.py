from cryptography.fernet import Fernet

from app.common.crypto import SecretCipher


def test_secret_cipher_round_trip_does_not_store_plaintext() -> None:
    cipher = SecretCipher(Fernet.generate_key().decode("ascii"))
    encrypted = cipher.encrypt("session-value")

    assert encrypted != "session-value"
    assert cipher.decrypt(encrypted) == "session-value"
