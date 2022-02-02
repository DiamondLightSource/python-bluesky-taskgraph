from unittest.mock import Mock

from ophyd import Device
from ophyd.sim import SynAxis

from python_bluesky_taskgraph.core.task import BlueskyTask


def mock_task(wrapped_task: BlueskyTask = None, name: str = "Mock task") -> BlueskyTask:
    wrapped_task = wrapped_task or BlueskyTask(name=name)
    task = Mock(wraps=wrapped_task)
    task._status = wrapped_task._status

    return task


def mock_device(device: Device = None, name: str = "Mock Device") -> Device:
    device = device or SynAxis(name=name)
    mock = Mock(wraps=device)

    def read():
        return device.read()

    mock.read.side_effect = read
    mock.name = device.name

    return mock
