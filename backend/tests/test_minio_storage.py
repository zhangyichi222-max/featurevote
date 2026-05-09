from app.clients import minio_storage


def test_public_base_url_falls_back_to_endpoint_and_bucket(monkeypatch) -> None:
    monkeypatch.setattr(minio_storage.settings, "minio_public_base_url", "")
    monkeypatch.setattr(minio_storage.settings, "minio_secure", False)
    monkeypatch.setattr(minio_storage.settings, "minio_endpoint", "192.168.8.65:9000")
    monkeypatch.setattr(minio_storage.settings, "minio_bucket", "featurevote")

    assert minio_storage._public_base_url() == "http://192.168.8.65:9000/featurevote"


def test_public_base_url_prefers_explicit_value(monkeypatch) -> None:
    monkeypatch.setattr(minio_storage.settings, "minio_public_base_url", "http://cdn.local/featurevote")

    assert minio_storage._public_base_url() == "http://cdn.local/featurevote"
