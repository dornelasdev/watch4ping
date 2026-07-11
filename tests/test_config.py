import pytest

from watch4ping.config import load_config, parse_target_config
from watch4ping.models import Target


def test_load_config_returns_empty_config_when_file_is_missing(tmp_path):
    config = load_config(tmp_path / "missing.toml")

    assert config.profiles == {}


def test_load_config_parses_profiles(tmp_path):
    path = tmp_path / "watch4ping.toml"
    path.write_text(
        """
[profile.home]
targets = ["router=192.168.1.1", "cloudflare=1.1.1.1"]
interval = 5
timeout = 2
fail_threshold = 4
""",
        encoding="utf-8",
    )

    config = load_config(path)
    profile = config.profiles["home"]

    assert profile.targets == (
        Target(label="router", host="192.168.1.1"),
        Target(label="cloudflare", host="1.1.1.1"),
    )
    assert profile.interval_seconds == 5
    assert profile.timeout_seconds == 2
    assert profile.fail_threshold == 4


def test_load_config_rejects_invalid_profile_values(tmp_path):
    path = tmp_path / "watch4ping.toml"
    path.write_text(
        """
[profile.home]
targets = []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(path)


def test_parse_target_config_accepts_labeled_targets():
    assert parse_target_config("router=192.168.1.1") == Target(
        label="router",
        host="192.168.1.1",
    )
