from src.postbase.platform.secret_store import DbEncryptedSecretStore


def test_db_encrypted_secret_store_roundtrip() -> None:
    store = DbEncryptedSecretStore("unit-test-key")
    encrypted = store.encrypt("super-secret")

    assert encrypted != "super-secret"
    assert store.decrypt(encrypted) == "super-secret"
