from dataclasses import dataclass
from typing import Generic, TypeVar

from ophyd import Device
from ophyd.status import Status

from python_bluesky_taskgraph.core.task import BlueskyTask
from python_bluesky_taskgraph.core.types import EmptyInput, Input, TaskOutput


def read_device(device: Device):
    return device.read()[device.name]["value"]


class NoOpTask(BlueskyTask[EmptyInput]):
    def organise_inputs(self, *args) -> EmptyInput:
        return EmptyInput()

    def _run_task(self, inputs: EmptyInput) -> TaskOutput:
        yield from self._add_callback_or_complete(None)


class ConditionalTask(BlueskyTask["ConditionalTask.ConditionalInputs"]):
    """
    Task with a condition based upon its arguments that can be resolved into a
    boolean of whether the task should run through one Plan or another/be skipped,
      e.g. if len(args) == 1 yield from plan1 else yield from plan2
    If a second plan isn't provided, the condition instead decides whether the task
    should be run or skipped.
    As the zip of the plans expected output names and its  output values truncates to
    the shortest list, if we provide no results, the DecisionEngine will not adjust
    any of its values, so any outputs provided by this task should be considered
    optional or unchanged from initial conditions.
    """

    ConditionalType = TypeVar("ConditionalType", bound=Input)
    FirstInputs = TypeVar("FirstInputs", bound=Input)
    SecondInputs = TypeVar("SecondInputs", bound=Input)

    @dataclass
    class ConditionalInputs(Input, Generic[ConditionalType, FirstInputs, SecondInputs]):
        condition_inputs: "ConditionalTask.ConditionalType"
        first_inputs: "ConditionalTask.FirstInputs"
        second_inputs: "ConditionalTask.SecondInputs"

    def __init__(
        self,
        name: str,
        first_task: BlueskyTask[FirstInputs],
        second_task: BlueskyTask[SecondInputs] = None,
    ):
        super().__init__(name)
        self._first_task: BlueskyTask = first_task
        self._second_task: BlueskyTask = second_task or NoOpTask(
            f"{first_task.name} skipped!"
        )

    def organise_inputs(self, *args) -> ConditionalInputs:
        return ConditionalTask.ConditionalInputs(*args)

    def _check_condition(self, condition_check_args: ConditionalType) -> bool:
        ...

    def propagate_status(self, status: Status) -> None:
        if isinstance(status.obj, BlueskyTask):
            self._overwrite_results(status.obj._results)
        else:
            self.add_result(status.obj)
        super().propagate_status(status)

    def _run_task(self, inputs: ConditionalInputs) -> TaskOutput:
        condition = self._check_condition(inputs.condition_inputs)
        task = self._first_task if condition else self._second_task
        args = inputs.first_inputs if condition else inputs.second_inputs
        self._logger.info(
            f"Condition was {condition}: running {task.name} with args {args}"
        )
        # Track the state of the plan we choose to run
        task.add_complete_callback(self.propagate_status)
        yield from task.execute(args)
