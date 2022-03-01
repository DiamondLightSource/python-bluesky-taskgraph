import logging
from typing import Any, Dict, Generator
from unittest.mock import call

from bluesky import Msg, RunEngine
from bluesky.plan_stubs import abs_set
from bluesky.suspenders import SuspenderBase
from ophyd import DeviceStatus
from ophyd.sim import SynAxis
from ophyd.utils import DestroyedError, DisconnectedError

from mocks import mock_device
from python_bluesky_taskgraph.core.decision_engine import (
    DecisionEngineControlObject,
    ExceptionTrackingSuspendCeil,
)
from python_bluesky_taskgraph.core.task import BlueskyTask, TaskFail, TaskStop
from python_bluesky_taskgraph.core.task_graph import TaskGraph
from python_bluesky_taskgraph.core.type_hints import TaskOutput
from python_bluesky_taskgraph.tasks.stub_tasks import SetTask

logging.basicConfig(level=logging.DEBUG)
EXCEPTIONAL_MOTOR = "Sticky Motor"
TASK_EXCEPTS_MOTOR = "Broken Motor"
SET_CALL = [call.set(7)]

"""
    RunEngine holds ControlObject, which generated DecisionEnginePlans, with their
    DecisionEngines.
    The DecisionEngines yield Messages from Tasks to the RunEngine, and the RunEngine
    translates messages into commands for Devices.
    Devices can have exceptions, which call back to the RunEngine, which calls back
    to the DecisionEnginePlan to try and solve them.
    Tasks can have exceptions, which either they should solve, or the exception is
    passed up to the DecisionEngine
"""


class RecoveringFromNonFatalExceptionSetTask(BlueskyTask[SetTask.SetDeviceInputs]):
    def __init__(self, name: str, fatal: bool):
        super().__init__(name)
        self.is_fatal = fatal

    """
    A Task with a known, non-fatal exception state that should cause the current task
    graph to fail and attempt the next loop.
    """

    def organise_inputs(self, *args: Any) -> SetTask.SetDeviceInputs:
        return SetTask.SetDeviceInputs(*args)

    def _run_task(self, inputs: SetTask.SetDeviceInputs) -> TaskOutput:
        if inputs.device.name is TASK_EXCEPTS_MOTOR:
            self._fail(TaskFail(self.name) if self.is_fatal else TaskStop(self.name))
        else:
            try:
                ret = yield from abs_set(inputs.device, inputs.value)
                yield from self._add_callback_or_complete(ret)
            except DisconnectedError:
                # Catches the exception passed back to us from the RunEngine
                self._fail(TaskStop(self.name))


class FailingDevice(SynAxis):
    def __init__(self, *, name, fatal=False, **kwargs):
        super().__init__(name=name, **kwargs)
        self.fatal = fatal

    def set(self, value) -> DeviceStatus:
        if self.fatal:
            raise DestroyedError()
        else:
            raise DisconnectedError()


class FailingDecisionEngineControlObject(DecisionEngineControlObject):
    def multiple_task_graphs(self) -> Generator[Msg, None, None]:
        for _ in range(5):
            if (
                not isinstance(self._exception_tracker, SuspenderBase)
                or not self._exception_tracker.tripped
            ):
                yield from self.decision_engine_plan(self._create_next_graph())

    def _create_next_graph(self, overrides: Dict[str, Any] = None) -> TaskGraph:
        if not overrides:
            overrides = self._known_values
        prior_task = SetTask("Prior task")
        failing_task = RecoveringFromNonFatalExceptionSetTask(
            "Failing Task", overrides.get("fatal", False)
        )
        future_task = SetTask("Future task")

        return TaskGraph(
            {
                prior_task: set(),
                failing_task: {prior_task},
                future_task: {failing_task},
            },
            {
                failing_task: ["second_device", "value"],
                prior_task: ["first_device", "value"],
                future_task: ["third_device", "value"],
            },
            {},
        )


def test_same_non_fatal_error_from_task_n_times_breaks_from_loop():
    re = RunEngine({})
    device_breaks_task = mock_device(name=TASK_EXCEPTS_MOTOR)
    working_device = mock_device(name="Counting device")
    control = FailingDecisionEngineControlObject(
        re,
        known_values={
            "first_device": working_device,
            "second_device": device_breaks_task,
            "third_device": working_device,
            "value": 7,
            "fatal": False,
        },
        exception_tracker=ExceptionTrackingSuspendCeil(2.5),
    )

    control.run_task_graphs()

    filtered_calls = [move for move in working_device.mock_calls if move in SET_CALL]
    # Called exactly 3 times: runs 1st task 3 times, never third task.
    assert filtered_calls == SET_CALL * 3
    # Call never makes it to device, exception is thrown in task.
    assert SET_CALL not in device_breaks_task.mock_calls


def test_same_non_fatal_error_from_device_n_times_breaks_from_loop():
    re = RunEngine({})
    broken_device = mock_device(
        wrapped_device=FailingDevice(name=EXCEPTIONAL_MOTOR, fatal=False)
    )
    working_device = mock_device(name="Counting device")
    control = FailingDecisionEngineControlObject(
        re,
        known_values={
            "first_device": working_device,
            "second_device": broken_device,
            "third_device": working_device,
            "value": 7,
            "fatal": False,
        },
        exception_tracker=ExceptionTrackingSuspendCeil(2.5),
    )

    control.run_task_graphs()
    # Working device called exactly 3 times: runs 1st task 3 times, never third task.
    # Broken device called exactly 3 times.
    for device in (working_device, broken_device):
        filtered_calls = [move for move in device.mock_calls if move in SET_CALL]
        assert filtered_calls == SET_CALL * 3


def test_fatal_error_from_task_breaks_from_loop():
    re = RunEngine({})
    device_breaks_task = mock_device(name=TASK_EXCEPTS_MOTOR)
    working_device = mock_device(name="Counting device")
    control = FailingDecisionEngineControlObject(
        re,
        known_values={
            "first_device": working_device,
            "second_device": device_breaks_task,
            "third_device": working_device,
            "value": 7,
            "fatal": True,
        },
        exception_tracker=ExceptionTrackingSuspendCeil(2.5),
    )
    control.run_task_graphs()

    # Working device called exactly 1 times: runs 1st task 1 times, never third task.
    filtered_calls = [move for move in working_device.mock_calls if move in SET_CALL]
    assert filtered_calls == SET_CALL
    assert SET_CALL not in device_breaks_task.mock_calls


def test_fatal_error_from_device_breaks_from_loop():
    re = RunEngine({})
    broken_device = mock_device(
        wrapped_device=FailingDevice(name=EXCEPTIONAL_MOTOR, fatal=True)
    )
    working_device = mock_device(name="Counting device")
    control = FailingDecisionEngineControlObject(
        re,
        known_values={
            "first_device": broken_device,
            "second_device": working_device,
            "third_device": working_device,
            "value": 7,
            "fatal": True,
        },
        exception_tracker=ExceptionTrackingSuspendCeil(2.5),
    )
    control.run_task_graphs()
    # Broken device called exactly 1 times: runs 1st task 1 times
    filtered_calls = [move for move in broken_device.mock_calls if move in SET_CALL]
    assert filtered_calls == SET_CALL
    assert SET_CALL not in working_device.mock_calls


def test_no_exception_to_completion():
    re = RunEngine({})
    first_device = mock_device(name="First device")
    second_device = mock_device(name="Second device")
    third_device = mock_device(name="Third device")
    control = FailingDecisionEngineControlObject(
        re,
        known_values={
            "first_device": first_device,
            "second_device": second_device,
            "third_device": third_device,
            "value": 7,
        },
        exception_tracker=ExceptionTrackingSuspendCeil(2.5),
    )
    control.run_task_graphs()

    for device in [first_device, second_device, third_device]:
        filtered_calls = [move for move in device.mock_calls if move in SET_CALL]
        assert filtered_calls == SET_CALL * 5
