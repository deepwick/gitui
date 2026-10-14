import re
import shutil
import subprocess
from pathlib import Path

import pytest

from deepwick_spec.ansi import runs, style_of
from deepwick_spec.check_port import check_port
from deepwick_spec.palette import load_palette
from deepwick_spec.tui import capture, tmux_available

REPO = Path(__file__).resolve().parents[1]
PALETTE = load_palette()
C = PALETTE.colors


def isolated_env(tmp_path, **extra):
    dirs = {"HOME": tmp_path / "home"}
    for kind in ("CONFIG", "DATA", "STATE", "CACHE"):
        dirs[f"XDG_{kind}_HOME"] = tmp_path / kind.lower()
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    env = {key: str(path) for key, path in dirs.items()}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    env.update({key: str(value) for key, value in extra.items()})
    return env


def make_repo(root):
    git = ["git", "-C", str(root), "-c", "user.name=Deepwick", "-c", "user.email=deepwick@example.invalid"]
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin"}
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, env=env)
    (root / "app.py").write_text('def greet(name):\n    return "Hello, " + name\n')
    (root / "notes.txt").write_text("Deepwick sample repository.\n")
    subprocess.run([*git, "add", "."], check=True, env=env)
    subprocess.run([*git, "commit", "-qm", "Initial commit"], check=True, env=env)
    subprocess.run([*git, "tag", "v0.1"], check=True, env=env)
    (root / "app.py").write_text('def greet(name):\n    return "Hi, " + name\n')
    subprocess.run([*git, "commit", "-qam", "Shorter greeting"], check=True, env=env)
    (root / "app.py").write_text('def greet(name):\n    return "Hey, " + name\n')
    (root / "new.py").write_text("print('new')\n")
    subprocess.run([*git, "add", "new.py"], check=True, env=env)
    (root / "untracked.txt").write_text("scratch\n")
    return root


requires_gitui = pytest.mark.skipif(not (tmux_available() and shutil.which("gitui")), reason="requires tmux and gitui")
COLORS = {
    "selected_tab": "blue", "command_fg": "foreground", "selection_bg": "selection", "selection_fg": "foreground",
    "cmdbar_bg": "surface", "disabled_fg": "muted", "diff_line_add": "green", "diff_line_delete": "red",
    "diff_file_added": "teal", "diff_file_removed": "red", "diff_file_moved": "magenta",
    "diff_file_modified": "blue", "commit_hash": "gold", "commit_time": "comment", "commit_author": "lightBlue",
    "danger_fg": "red", "push_gauge_bg": "blue", "push_gauge_fg": "background", "tag_fg": "magenta",
    "branch_fg": "teal", "block_title_focused": "blue",
}


def entries():
    path = REPO / "deepwick.ron"
    assert path.is_file(), "deepwick.ron missing"
    return dict(re.findall(r"^\s*(\w+):\s*Some\((.*?)\),?\s*$", path.read_text(encoding="utf-8"), re.M))


def test_sets_every_color_key():
    assert set(entries()) == set(COLORS) | {"use_selection_fg"}


def test_colors():
    e = entries()
    for key, color in COLORS.items():
        assert e[key] == f'"{C[color]}"', key


def test_selected_rows_keep_their_colors():
    assert entries()["use_selection_fg"] == "false"


def gitui(tmp_path, **kwargs):
    repo = make_repo(tmp_path / "repo")
    log = tmp_path / "gitui.log"
    text = capture(
        f"cd {repo} && gitui -t {REPO / 'deepwick.ron'} --logfile {log}",
        isolated_env(tmp_path), size=(120, 30), **kwargs,
    )
    assert "theme error" not in (log.read_text() if log.exists() else "")
    return text


@requires_gitui
def test_status_tab(tmp_path):
    text = gitui(tmp_path, wait_for="untracked.txt")
    # gitui draws the status marker and the name as one run: "+ untracked.txt".
    assert style_of(text, "+ untracked.txt")["fg"] == C["teal"].lower()
    assert any(s["bg"] == C["selection"].lower() for _, s in runs(text))
    assert any(s["fg"] == C["blue"].lower() and s["bold"] for _, s in runs(text))


@requires_gitui
def test_log_tab(tmp_path):
    text = gitui(tmp_path, wait_for="untracked.txt", keys=("2",), after="Initial commit")
    fgs = {s["fg"] for _, s in runs(text)}
    assert {C["gold"].lower(), C["lightBlue"].lower(), C["comment"].lower(), C["magenta"].lower()} <= fgs


def test_port_conventions():
    assert check_port(REPO, PALETTE.allowed_hex()) == []
