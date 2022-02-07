from unittest.mock import MagicMock, PropertyMock

from ophyd import Device
from ophyd.sim import SynAxis

from python_bluesky_taskgraph.core.task import BlueskyTask
from python_bluesky_taskgraph.tasks.behavioural_tasks import NoOpTask


def mock_task(wrapped_task: BlueskyTask = None, name: str = "Mock task") -> BlueskyTask:
    if wrapped_task is None:
        wrapped_task = NoOpTask(name)
    task = MagicMock(wraps=wrapped_task)
    task.execute = MagicMock(wraps=wrapped_task.execute)
    task.get_results = MagicMock(wraps=wrapped_task.get_results)
    task.status = PropertyMock(wraps=wrapped_task.status)
    task.complete = PropertyMock(wraps=wrapped_task.complete)
    task.add_complete_callback = MagicMock(wraps=wrapped_task.add_complete_callback)
    return task


def mock_device(wrapped_device: Device = None, name: str = "Mock Device") -> Device:
    if wrapped_device is None:
        wrapped_device = SynAxis(name=name)
    device = MagicMock(wraps=wrapped_device)
    device.read = MagicMock(wraps=wrapped_device.read)
    device.name = name or wrapped_device.name
    return device
