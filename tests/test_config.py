"""Offline security-boundary tests using synthetic identifiers and credentials."""

import pytest

from feishu_bitable_mcp.config import BitableError, Settings, Target

EXAMPLE_URL = (
    "https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01&view=vewDemoView1"
)
AUTH_TOKEN = "synthetic-mcp-auth-token-0000000000000000"
ENVIRONMENT_KEYS = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "MCP_AUTH_TOKEN",
    "FEISHU_ENABLE_WRITES",
    "FEISHU_READ_TABLE_URLS",
    "FEISHU_WRITE_TABLE_URLS",
)


@pytest.fixture
def configured_env(monkeypatch):
    """Never inherit local credentials or authorization policies into a test."""
    for key in ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FEISHU_APP_ID", "synthetic-application-id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "synthetic-application-secret")
    return monkeypatch


@pytest.mark.parametrize(
    "url",
    [
        EXAMPLE_URL,
        EXAMPLE_URL.replace("example.feishu.cn", "feishu.cn"),
        EXAMPLE_URL.replace("example.feishu.cn", "EXAMPLE.FEISHU.CN"),
        EXAMPLE_URL.replace("?table", "/?table"),
        EXAMPLE_URL.replace("&view=vewDemoView1", ""),
    ],
)
def test_url_extracts_target_without_fetching(url):
    target = Target.parse(url)
    assert target.app_token == "DemoBaseToken0001"
    assert target.table_id == "tblDemoTable01"
    assert target.key == ("DemoBaseToken0001", "tblDemoTable01")
    assert target.identifiers() == {
        "app_token": "DemoBaseToken0001",
        "table_id": "tblDemoTable01",
        "view_id": "vewDemoView1" if "&view=" in url else None,
    }


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        42,
        EXAMPLE_URL.replace("https://", "http://"),
        EXAMPLE_URL.replace("https://", "file://"),
        EXAMPLE_URL.replace("example.feishu.cn", "127.0.0.1"),
        EXAMPLE_URL.replace("example.feishu.cn", "localhost"),
        EXAMPLE_URL.replace("example.feishu.cn", "feishu.cn.example.com"),
        EXAMPLE_URL.replace("example.feishu.cn", "notfeishu.cn"),
        EXAMPLE_URL.replace("example.feishu.cn", "example.feishu.cn."),
        EXAMPLE_URL.replace("example.feishu.cn", "example.feishu%2ecn"),
        EXAMPLE_URL.replace("example.feishu.cn", "example.feishu.cn@evil.example"),
        EXAMPLE_URL.replace("example.feishu.cn", "user@example.feishu.cn"),
        EXAMPLE_URL.replace("example.feishu.cn", "user:password@example.feishu.cn"),
        EXAMPLE_URL.replace("example.feishu.cn", "@example.feishu.cn"),
        EXAMPLE_URL.replace("example.feishu.cn", "example.feishu.cn:443"),
        EXAMPLE_URL.replace("example.feishu.cn", "example.feishu.cn:8000"),
        EXAMPLE_URL.replace("example.feishu.cn", "example.feishu.cn:invalid"),
        EXAMPLE_URL.replace("/base/", "/wiki/"),
        EXAMPLE_URL.replace("/base/", "/base%2f"),
        EXAMPLE_URL.replace("/base/", "/%62ase/"),
        EXAMPLE_URL.replace("/base/", "/base/../base/"),
        EXAMPLE_URL.replace("/base/", "\\base\\"),
        EXAMPLE_URL.replace("DemoBaseToken0001", "Demo%42aseToken0001"),
        EXAMPLE_URL.replace("DemoBaseToken0001", "DemoBaseToken0001/extra"),
        EXAMPLE_URL.replace("?table=tblDemoTable01&view=vewDemoView1", ""),
        EXAMPLE_URL.replace("table=tblDemoTable01", "table="),
        EXAMPLE_URL.replace("table=tblDemoTable01", "table=arbitrary"),
        EXAMPLE_URL + "&table=tblDemoTable01",
        EXAMPLE_URL + "&%74able=tblDemoTable01",
        EXAMPLE_URL + "&view=vewDemoView1",
        EXAMPLE_URL.replace("view=vewDemoView1", "view="),
        EXAMPLE_URL.replace("view=vewDemoView1", "view=invalid"),
        EXAMPLE_URL + "#fragment",
        " " + EXAMPLE_URL,
        EXAMPLE_URL + " ",
        EXAMPLE_URL + "\n",
        EXAMPLE_URL + "\x7f",
        EXAMPLE_URL.replace("/base/", "/ba\tse/"),
        EXAMPLE_URL.replace("/base/", "/ba\x00se/"),
        EXAMPLE_URL + "&extra=" + "x" * 4096,
        EXAMPLE_URL + "".join(f"&key{i}=value" for i in range(31)),
    ],
)
def test_rejects_unsafe_or_ambiguous_urls(url):
    with pytest.raises(BitableError):
        Target.parse(url)


def test_settings_repr_does_not_disclose_credentials():
    settings = Settings("sensitive-app-id", "sensitive-app-secret", auth_token=AUTH_TOKEN)
    representation = repr(settings)
    assert "sensitive-app-id" not in representation
    assert "sensitive-app-secret" not in representation
    assert AUTH_TOKEN not in representation


def test_writes_are_off_by_default(configured_env):
    settings = Settings.from_env()
    assert settings.enable_writes is False
    assert settings.auth_token == ""
    target = Target.parse(EXAMPLE_URL)
    settings.authorize(target)
    with pytest.raises(BitableError):
        settings.authorize(target, write=True)


@pytest.mark.parametrize("missing", ["FEISHU_APP_ID", "FEISHU_APP_SECRET"])
def test_missing_application_credentials_rejected(configured_env, missing):
    configured_env.delenv(missing)
    with pytest.raises(BitableError, match="FEISHU_APP_ID and FEISHU_APP_SECRET"):
        Settings.from_env()


@pytest.mark.parametrize("flag", ["1", "yes", "on", "enabled", ""])
def test_write_opt_in_rejects_ambiguous_boolean(configured_env, flag):
    configured_env.setenv("FEISHU_ENABLE_WRITES", flag)
    with pytest.raises(BitableError, match="true or false"):
        Settings.from_env()


@pytest.mark.parametrize("auth_token", ["", "short", "x" * 31])
def test_writes_require_strong_authentication(configured_env, auth_token):
    configured_env.setenv("FEISHU_ENABLE_WRITES", "true")
    configured_env.setenv("FEISHU_WRITE_TABLE_URLS", EXAMPLE_URL)
    configured_env.setenv("MCP_AUTH_TOKEN", auth_token)
    with pytest.raises(BitableError):
        Settings.from_env()


def test_writes_require_explicit_target_allowlist(configured_env):
    configured_env.setenv("FEISHU_ENABLE_WRITES", "true")
    configured_env.setenv("MCP_AUTH_TOKEN", AUTH_TOKEN)
    with pytest.raises(BitableError, match="FEISHU_WRITE_TABLE_URLS"):
        Settings.from_env()


def test_write_policy_is_scoped_to_base_and_table(configured_env):
    configured_env.setenv("FEISHU_ENABLE_WRITES", "true")
    configured_env.setenv("MCP_AUTH_TOKEN", AUTH_TOKEN)
    configured_env.setenv("FEISHU_WRITE_TABLE_URLS", EXAMPLE_URL)
    settings = Settings.from_env()
    target = Target.parse(EXAMPLE_URL)
    settings.authorize(target, write=True)
    settings.authorize(Target(target.app_token, target.table_id), write=True)
    for other in [
        Target("OtherDemoBase0001", target.table_id),
        Target(target.app_token, "tblOtherDemo01"),
    ]:
        with pytest.raises(BitableError):
            settings.authorize(other, write=True)


def test_read_allowlist_applies_to_both_reads_and_writes(configured_env):
    other_url = EXAMPLE_URL.replace("tblDemoTable01", "tblOtherDemo01")
    configured_env.setenv("FEISHU_ENABLE_WRITES", "true")
    configured_env.setenv("MCP_AUTH_TOKEN", AUTH_TOKEN)
    configured_env.setenv("FEISHU_READ_TABLE_URLS", EXAMPLE_URL)
    configured_env.setenv("FEISHU_WRITE_TABLE_URLS", EXAMPLE_URL + "," + other_url)
    settings = Settings.from_env()
    settings.authorize(Target.parse(EXAMPLE_URL))
    settings.authorize(Target.parse(EXAMPLE_URL), write=True)
    for write in [False, True]:
        with pytest.raises(BitableError, match="FEISHU_READ_TABLE_URLS"):
            settings.authorize(Target.parse(other_url), write=write)


def test_malformed_allowlist_cannot_silently_expand_access(configured_env):
    configured_env.setenv("FEISHU_READ_TABLE_URLS", "*")
    with pytest.raises(BitableError):
        Settings.from_env()


def test_allowlist_deduplicates_targets_across_views(configured_env):
    configured_env.setenv(
        "FEISHU_READ_TABLE_URLS",
        EXAMPLE_URL + ", " + EXAMPLE_URL.replace("&view=vewDemoView1", ""),
    )
    settings = Settings.from_env()
    assert settings.read_tables == frozenset({Target.parse(EXAMPLE_URL).key})
