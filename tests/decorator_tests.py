from dataclasses import dataclass
from typing import Any, Dict, Generator
from unittest.mock import ANY, MagicMock, call

from bluesky import Msg, RunEngine
from ophyd import Device
from ophyd.sim import SynAxis

from python_bluesky_taskgraph.core.decision_engine import decision_engine_plan
from python_bluesky_taskgraph.core.task import BlueskyTask, task_stage_decorator
from python_bluesky_taskgraph.core.task_graph import TaskGraph, taskgraph_run_decorator
from python_bluesky_taskgraph.core.type_hints import Input, InputType
from python_bluesky_taskgraph.tasks.behavioural_tasks import NoOpTask


def generate_basic_taskgraph():
    return TaskGraph({NoOpTask("NoOp"): set()}, {}, {})


@taskgraph_run_decorator
def generate_decorated_taskgraph():
    return generate_basic_taskgraph()


class TaskWithDeviceAndOtherComponents(
    BlueskyTask["TaskWithDeviceAndOtherComponents.Params"]
):
    @dataclass
    class Params(Input):
        device: Device
        location: Any
        second_device: Device
        missing_device: Device
        default_device: Device = MagicMock(wraps=SynAxis(name="def"))
        missing_default_device: Device = None

    def organise_inputs(self, *args: Any) -> Params:
        return TaskWithDeviceAndOtherComponents.Params(*args)

    def _run_task(self, inputs: InputType) -> Generator[Msg, None, None]:
        yield from self._add_callback_or_complete(None)


def test_no_run_opened():
    RE = RunEngine({})
    run_starts = RE._run_start_uids = MagicMock()
    RE(decision_engine_plan(generate_basic_taskgraph(), {}))

    assert not call.append(ANY) in run_starts.method_calls


def test_run_opened_with_decorator():
    RE = RunEngine({})
    run_starts = RE._run_start_uids = MagicMock()
    RE(decision_engine_plan(generate_decorated_taskgraph(), {}))

    assert call.append(ANY) in run_starts.method_calls


def get_expected_arguments() -> Dict[str, Any]:
    return {
        "first_device": MagicMock(wraps=SynAxis(name="first_device")),
        "second_device": MagicMock(wraps=SynAxis(name="second_device")),
        "missing_device": None,
        "location": MagicMock(wraps=7),
        "not_called": MagicMock(wraps=SynAxis(name="second_device")),
    }


def get_non_staging_taskgraph() -> TaskGraph:
    task = TaskWithDeviceAndOtherComponents("NoName")
    return TaskGraph(
        {task: set()},
        {task: ["first_device", "location", "second_device", "missing_device"]},
        {task: []},
    )


def get_staging_taskgraph() -> TaskGraph:
    @task_stage_decorator
    def get_task():
        return TaskWithDeviceAndOtherComponents("NoName")

    task = get_task()
    return TaskGraph(
        {task: set()},
        {task: ["first_device", "location", "second_device", "missing_device"]},
        {task: []},
    )


def test_no_devices_staged():
    args = get_expected_arguments()
    RE = RunEngine({})
    RE(decision_engine_plan(generate_basic_taskgraph(), args))

    assert not call.stage(ANY) in args["first_device"].method_calls
    assert not call.stage(ANY) in args["second_device"].method_calls
    assert not call.stage(ANY) in args["location"].method_calls


def test_only_devices_staged():
    args = get_expected_arguments()
    RE = RunEngine({})
    RE(decision_engine_plan(get_staging_taskgraph(), args))

    assert call.stage() in args["first_device"].method_calls
    assert call.stage() in args["second_device"].method_calls
    assert not call.stage() in args["location"].method_calls
