import pytest

from app.config import ConfigError, load_config

VALID_ENV = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key-value",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key-value",
    "SUPABASE_DB_HOST": "db.example.supabase.co",
    "SUPABASE_DB_PASSWORD": "db-password-value",
    "OPENAI_API_KEY": "sk-test-value",
    "OPENAI_MODEL": "gpt-test-model",
}


def test_valid_config_loads():
    config = load_config(VALID_ENV)
    assert str(config.supabase.url) == "https://example.supabase.co/"
    assert config.supabase.anon_key == "anon-key-value"
    assert config.supabase.db_host == "db.example.supabase.co"
    assert config.supabase.db_port == 5432
    assert config.supabase.db_user == "postgres"
    assert config.openai.model == "gpt-test-model"
    assert config.expo.access_token is None
    assert config.render.is_render is False


def test_valid_config_with_optional_fields_set():
    env = {
        **VALID_ENV,
        "SUPABASE_DB_PORT": "6543",
        "SUPABASE_DB_USER": "postgres.myproject",
        "EXPO_ACCESS_TOKEN": "expo-token",
        "RENDER_SERVICE_ID": "srv-123",
        "RENDER_GIT_COMMIT": "abc123",
    }
    config = load_config(env)
    assert config.supabase.db_port == 6543
    assert config.supabase.db_user == "postgres.myproject"
    assert config.expo.access_token == "expo-token"
    assert config.render.service_id == "srv-123"
    assert config.render.is_render is True


@pytest.mark.parametrize(
    "missing_key,expected_env_var",
    [
        ("SUPABASE_URL", "SUPABASE_URL"),
        ("SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY"),
        ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
        ("SUPABASE_DB_HOST", "SUPABASE_DB_HOST"),
        ("SUPABASE_DB_PASSWORD", "SUPABASE_DB_PASSWORD"),
        ("OPENAI_API_KEY", "OPENAI_API_KEY"),
        ("OPENAI_MODEL", "OPENAI_MODEL"),
    ],
)
def test_each_missing_required_field_fails_with_clear_message(missing_key, expected_env_var):
    env = {k: v for k, v in VALID_ENV.items() if k != missing_key}
    with pytest.raises(ConfigError) as exc_info:
        load_config(env)
    assert expected_env_var in str(exc_info.value)


def test_all_required_fields_missing_reports_every_problem_at_once():
    with pytest.raises(ConfigError) as exc_info:
        load_config({})
    message = str(exc_info.value)
    for env_var in [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_DB_HOST",
        "SUPABASE_DB_PASSWORD",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
    ]:
        assert env_var in message


def test_invalid_supabase_url_fails_with_clear_message_not_a_stack_trace():
    env = {**VALID_ENV, "SUPABASE_URL": "not-a-url"}
    with pytest.raises(ConfigError) as exc_info:
        load_config(env)
    assert "SUPABASE_URL" in str(exc_info.value)


def test_error_message_never_contains_secret_values():
    env = {**VALID_ENV, "OPENAI_API_KEY": ""}
    with pytest.raises(ConfigError) as exc_info:
        load_config(env)
    message = str(exc_info.value)
    assert "sk-test-value" not in message
    assert VALID_ENV["SUPABASE_SERVICE_ROLE_KEY"] not in message
    assert VALID_ENV["SUPABASE_DB_PASSWORD"] not in message
