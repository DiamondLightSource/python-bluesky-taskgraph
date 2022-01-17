from datetime import time
from unittest.mock import Mock

from bluesky import Msg
from ophyd import Device
from ophyd.sim import SynAxis

from src.bluesky_taskgraph_runner.core.task import TaskStatus, BlueskyTask
from src.bluesky_taskgraph_runner.core.types import PlanArgs, PlanOutput


def mock_task(wrapped_task: BlueskyTask = None, name: str = "Mock task") -> BlueskyTask:
    wrapped_task = wrapped_task or BlueskyTask(name=name)
    task = Mock(wraps=wrapped_task)

    def _run_task(args=None):
        task._status.set_finished()
        yield Msg('null')

    def started():
        return task._status is not None and isinstance(task._status, TaskStatus)

    def complete():
        return started() and task._status.done

    def execute(args: PlanArgs) -> PlanOutput:
        task._status = TaskStatus(task=task)
        wrapped_task._status = task._status
        task._logger.info(msg=f"Task {task.name} started at {time()}, with args: {args}")
        yield from task._run_task(*args)

    task.execute.side_effect = execute
    task._run_task.side_effect = _run_task
    task.started.side_effect = started
    task.complete.side_effect = complete
    return task


def mock_device(device: Device = None, name: str = "Mock Device") -> Device:
    device = device or SynAxis(name=name)
    mock = Mock(wraps=device)

    def read():
        return device.read()

    mock.read.side_effect = read
    mock.name = device.name

    return mock
