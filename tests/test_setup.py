import json
import subprocess
import sys
import tomllib

import pytest

from print3d import setup
from print3d.paths import skill_dir


def _apply(home, agents, which=lambda _: None, run=None):
    for change in setup.plan(agents, home=home, which=which, run=run or subprocess.run):
        change.apply()


def test_the_server_runs_isolated_from_the_current_directory():
    # Agents start MCP servers in a project folder; without -I a ssl.py or json.py there would run inside print3d.
    assert setup.server_command() == [sys.executable, "-I", "-m", "print3d", "mcp"]


def test_only_agents_present_are_planned(tmp_path):
    (tmp_path / ".cursor").mkdir()
    which = {"codex": "/bin/codex"}.get
    assert setup.detect(tmp_path, which) == ["codex", "cursor"]


def test_codex_section_is_added_once_and_keeps_the_rest(tmp_path):
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text('model = "o5"\n\n[mcp_servers.other]\ncommand = "x"\n')
    _apply(tmp_path, ["codex"])
    _apply(tmp_path, ["codex"])
    text = config.read_text()
    assert text.count("[mcp_servers.print3d]") == 1
    assert 'model = "o5"' in text and "[mcp_servers.other]" in text
    assert json.dumps(sys.executable) in text
    assert tomllib.loads(text)["mcp_servers"]["print3d"]["args"] == ["-I", "-m", "print3d", "mcp"]
    assert list(config.parent.glob("config.toml.print3d-backup-*"))


def test_codex_update_preserves_windows_command_escapes(tmp_path, monkeypatch):
    command = r"C:\Users\Alice\Python\python.exe"
    monkeypatch.setattr(setup, "server_command", lambda: [command, "-m", "print3d", "mcp"])
    config = tmp_path / "config.toml"
    setup._merge_codex_toml(config)
    setup._merge_codex_toml(config)
    server = tomllib.loads(config.read_text())["mcp_servers"]["print3d"]
    assert server == {"command": command, "args": ["-m", "print3d", "mcp"]}


@pytest.mark.parametrize("header", [
    "[mcp_servers.print3d] # existing server",
    "  [mcp_servers.print3d] \t# existing server",
])
def test_codex_update_accepts_comments_and_keeps_following_tables(tmp_path, monkeypatch, header):
    monkeypatch.setattr(setup, "server_command", lambda: ["/usr/bin/python", "-m", "print3d", "mcp"])
    config = tmp_path / "config.toml"
    other = '  [mcp_servers.other] # keep this comment\ncommand = "other-server"\n'
    config.write_text(f'model = "example"\n{header}\ncommand = "/old/python"\n\n{other}')
    setup._merge_codex_toml(config)
    text = config.read_text()
    parsed = tomllib.loads(text)
    assert parsed["model"] == "example"
    assert parsed["mcp_servers"] == {
        "print3d": {"command": "/usr/bin/python", "args": ["-m", "print3d", "mcp"]},
        "other": {"command": "other-server"},
    }
    assert other in text


@pytest.mark.parametrize("original", [
    "[not valid TOML",
    # A valid spelling the text editor cannot recognize must not become a duplicate table.
    '[mcp_servers."print3d"]\ncommand = "old"\n',
])
def test_codex_invalid_or_unsupported_toml_is_left_alone(tmp_path, original):
    config = tmp_path / "config.toml"
    config.write_text(original)
    with pytest.raises(setup.SetupError, match="TOML"):
        setup._merge_codex_toml(config)
    assert config.read_text() == original
    assert not list(tmp_path.glob("config.toml.print3d-backup-*"))


def test_json_configs_keep_other_servers(tmp_path):
    settings = tmp_path / ".gemini" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
    _apply(tmp_path, ["gemini"])
    config = json.loads(settings.read_text())
    assert config["theme"] == "dark"
    assert set(config["mcpServers"]) == {"other", "print3d"}
    assert config["mcpServers"]["print3d"]["args"] == ["-I", "-m", "print3d", "mcp"]


def test_broken_json_is_left_alone(tmp_path):
    mcp = tmp_path / ".cursor" / "mcp.json"
    mcp.parent.mkdir()
    mcp.write_text("{not json")
    with pytest.raises(setup.SetupError):
        _apply(tmp_path, ["cursor"])
    assert mcp.read_text() == "{not json"


def test_claude_gets_the_skill_linked_and_the_server_added(tmp_path):
    old = tmp_path / ".claude" / "skills" / "print3d"
    old.mkdir(parents=True)
    calls = []

    def run(cmd, **_):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    _apply(tmp_path, ["claude"], which={"claude": "/bin/claude"}.get, run=run)
    assert old.resolve() == skill_dir()
    assert list(old.parent.glob("print3d.print3d-backup-*"))
    assert calls[-1][:6] == ["/bin/claude", "mcp", "add", "--scope", "user", "print3d"]
    assert calls[-1][6:] == ["--", sys.executable, "-I", "-m", "print3d", "mcp"]


def test_hermes_gets_the_skill_linked_and_the_server_added_once(tmp_path):
    hermes = tmp_path / ".hermes"
    (hermes / "skills").mkdir(parents=True)
    (hermes / "skills" / "print3d").symlink_to(tmp_path / "gone")
    config = hermes / "config.yaml"
    config.write_text(
        "model: x\n"
        "mcp_servers:\n"
        "  other:\n"
        "    command: npx\n"
        "\n"
        "  print3d:\n"
        "    command: /old/python\n"
        "    args: [-m, print3d, mcp]\n"
        "skills:\n"
        "  disabled: []\n"
    )
    _apply(tmp_path, ["hermes"])
    _apply(tmp_path, ["hermes"])
    text = config.read_text()
    assert (hermes / "skills" / "print3d").resolve() == skill_dir()
    assert text.count("  print3d:") == 1 and "/old/python" not in text
    assert json.dumps(sys.executable) in text and 'args: ["-I", "-m", "print3d", "mcp"]' in text
    assert "  other:\n    command: npx\n" in text
    assert text.startswith("model: x\n") and text.endswith("skills:\n  disabled: []\n")


def test_hermes_config_without_servers_gets_the_section(tmp_path):
    config = tmp_path / ".hermes" / "config.yaml"
    config.parent.mkdir()
    config.write_text("model: x\nmcp_servers: {}\n")
    _apply(tmp_path, ["hermes"])
    assert config.read_text().startswith("model: x\nmcp_servers:\n  print3d:\n")
