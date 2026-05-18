import os

from app.core import config


def test_dotenv_values_take_priority_over_bashrc(monkeypatch, tmp_path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "MINIO_ENDPOINT=dotenv-minio:9000",
                "MINIO_ACCESS_KEY='dotenv-access'",
                'MINIO_PUBLIC_BASE_URL="http://dotenv.example/featurevote"',
            ]
        ),
        encoding="utf-8",
    )
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text(
        "\n".join(
            [
                "export MINIO_ENDPOINT=bashrc-minio:9000",
                "export MINIO_ACCESS_KEY='bashrc-access'",
                'export MINIO_PUBLIC_BASE_URL="http://minio.example/featurevote"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("MINIO_ENDPOINT", "process-minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "process-access")
    monkeypatch.setenv("MINIO_PUBLIC_BASE_URL", "http://process/featurevote")

    config.get_settings.cache_clear()
    settings = config.get_settings()

    assert os.environ["MINIO_ENDPOINT"] == "dotenv-minio:9000"
    assert settings.minio_endpoint == "dotenv-minio:9000"
    assert settings.minio_access_key == "dotenv-access"
    assert settings.minio_public_base_url == "http://dotenv.example/featurevote"


def test_bashrc_minio_values_match_server_export_format(monkeypatch, tmp_path) -> None:
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text(
        "\n".join(
            [
                "export MINIO_ENDPOINT='192.168.8.65:9000'",
                "export MINIO_ACCESS_KEY='minioadmin'",
                "export MINIO_SECRET_KEY='minioadmin'",
                "export MINIO_SECURE='false'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("MINIO_PUBLIC_BASE_URL", raising=False)

    config.get_settings.cache_clear()
    settings = config.get_settings()

    assert settings.minio_endpoint == "192.168.8.65:9000"
    assert settings.minio_access_key == "minioadmin"
    assert settings.minio_secret_key == "minioadmin"
    assert settings.minio_bucket == "featurevote"
    assert settings.minio_secure is False
    assert settings.minio_public_base_url == ""
