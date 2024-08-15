import subprocess
import sys

from bluesky_taskgraph import __version__


def test_cli_version():
    cmd = [sys.executable, "-m", "bluesky_taskgraph", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
