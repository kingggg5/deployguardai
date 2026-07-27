from app.config import Settings


def test_comma_separated_cors_origins_are_read_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:4300,http://localhost:4300",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "http://127.0.0.1:4300",
        "http://localhost:4300",
    ]


def test_postgresql_database_url_uses_psycopg_driver() -> None:
    settings = Settings(
        database_url="postgresql://deployguard:secret@db/deployguard",
        _env_file=None,
    )

    assert settings.database_url == (
        "postgresql+psycopg://deployguard:secret@db/deployguard"
    )
