from app.kubernetes.redact import REDACTED, redact


def test_redacts_url_credentials():
    out = redact("connecting to postgres://app:hunter2@db:5432/orders")
    assert "hunter2" not in out
    assert "postgres://app:" in out and "@db:5432/orders" in out


def test_redacts_secret_env_assignments():
    out = redact("DB_PASSWORD=s3cr3t API_KEY=abc123 LOG_LEVEL=debug")
    assert "s3cr3t" not in out and "abc123" not in out
    assert "LOG_LEVEL=debug" in out


def test_redacts_tokens_and_keys():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.c2lnbmF0dXJlLXZhbHVl"
    for secret in (
        f"Authorization: Bearer {jwt}",
        jwt,
        "aws key AKIAABCDEFGHIJKLMNOP",
        "token ghp_" + "a" * 36,
        "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----",
    ):
        assert REDACTED in redact(secret), secret


def test_keeps_diagnostic_prose():
    for line in (
        "Error: missing DATABASE_URL environment variable",
        "error: unauthorized: invalid credentials",
        "token: expired",
        "Back-off pulling image nginx:does-not-exist",
    ):
        assert redact(line) == line
