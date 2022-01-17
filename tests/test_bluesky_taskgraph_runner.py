import subprocess
import sys

from src.bluesky_taskgraph_runner import __version__


def test_cli_version():
    cmd = [sys.executable, "-m", "bluesky_taskgraph_runner", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
