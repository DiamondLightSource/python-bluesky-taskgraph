from typing import Dict, Any
from unittest.mock import call

from bluesky import RunEngine
from bluesky.suspenders import SuspendCeil
from ophyd import DeviceStatus, Signal
from ophyd.sim import SynAxis
from ophyd.utils import DestroyedError

from python_bluesky_taskgraph.core.decision_engine import DecisionEngineControlObject
from python_bluesky_taskgraph.core.task import TaskStop, TaskFail
from python_bluesky_taskgraph.core.task_graph import TaskGraph
from python_bluesky_taskgraph.tasks.stub_tasks import SetTask
from mocks import mock_device


class FailingDevice(SynAxis):

    def __init__(self, name, fatal_exception=False):
        super().__init__(name=name, delay=3)
        self.exception = TaskFail if fatal_exception else TaskStop

    def set(self, value):
        st = DeviceStatus(self)
        st.set_exception(self.exception())
        return st


class FailingDecisionEngineControlObject(DecisionEngineControlObject):

    def __init__(self, run_engine: RunEngine, known_values: Dict[str, Any] = None):
        super().__init__(run_engine=run_engine, known_values=known_values)
        self._count = Signal(name="Run tasks 5 times at most")
        self._count.value = 0
        run_engine.install_suspender(SuspendCeil(signal=self._count, suspend_thresh=5))

    def run_task_graphs(self) -> None:
        for _ in range(5):
            self._run_engine(self.decision_engine_plan(self._create_next_graph()))
            self._count.value += 1

    def _create_next_graph(self, overrides: Dict[str, Any] = None) -> TaskGraph:
        prior_task = SetTask("Prior task")
        failing_task = RecoveringFromNonFatalExceptionSetTask("Failing Task")
        future_task = SetTask("Future task")

        return TaskGraph({prior_task: [],
                          failing_task: [prior_task],
                          future_task: [failing_task]},
                         {failing_task: ["second_device", "value"],
                          prior_task: ["first_device", "value"],
                          future_task: ["third_device", "value"]}, {})


class RecoveringFromNonFatalExceptionSetTask(SetTask):
    """
    A Task with a known, non-fatal exception state that should cause the current task
    graph to fail and attempt the next loop.
    """

    def _handle_exception(self, exception: Exception):
        if isinstance(exception, DestroyedError):
            exception = TaskStop()
        self._status.set_exception(exception)


# TODO: Breaks after one
# def test_same_non_fatal_error_n_times_breaks_from_loop():
#     re = RunEngine({})
#     broken_device = mock_device(FailingDevice("Sticky motor", fatal_exception=False))
#     working_device = mock_device(name="Counting device")
#     control = FailingDecisionEngineControlObject(re,
#                                                  known_values=
#                                                  {"first_device": working_device,
#                                                   "second_device": broken_device,
#                                                   "third_device": working_device,
#                                                   "value": 7})
#
#     try:
#         control.run_task_graphs()
#     except FailedStatus:
#         expected_calls = [call.set(7)] * 3
#
#         for device in [broken_device, working_device]:
#             filtered_calls = [calls for calls in device.mock_calls
#                               if calls in expected_calls]
#             assert(filtered_calls == expected_calls)


# TODO: Flaky
# def test_fatal_error_breaks_from_loop():
#     re = RunEngine({})
#     broken_device = mock_device(FailingDevice("Sticky motor", fatal_exception=True))
#     working_device = mock_device(name="Counting device")
#     control = FailingDecisionEngineControlObject(re,
#                                                  known_values={
#                                                      "first_device": working_device,
#                                                      "second_device": broken_device,
#                                                      "third_device": working_device,
#                                                      "value": 7})
#     try:
#         control.run_task_graphs()
#     except FailedStatus:
#         expected_calls = [call.set(7)]
#
#         for device in [broken_device, working_device]:
#             filtered_calls = [calls for calls in device.mock_calls
#                               if calls in expected_calls]
#             assert(filtered_calls == expected_calls)


def test_no_exception_to_completion():
    re = RunEngine({})
    first_device = mock_device(name="First device")
    second_device = mock_device(name="Second device")
    third_device = mock_device(name="Third device")
    control = FailingDecisionEngineControlObject(re,
                                                 known_values={
                                                     "first_device": first_device,
                                                     "second_device": second_device,
                                                     "third_device": third_device,
                                                     "value": 7})
    control.run_task_graphs()

    expected_calls = [call.set(7)] * 5

    for device in [first_device, second_device, third_device]:
        filtered_calls = [calls for calls in device.mock_calls
                          if calls in expected_calls]
        assert (filtered_calls == expected_calls)
