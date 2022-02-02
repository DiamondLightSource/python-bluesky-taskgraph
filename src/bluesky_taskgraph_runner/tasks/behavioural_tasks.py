from ophyd import Device

from src.bluesky_taskgraph_runner.core.task import BlueskyTask, TaskStatus
from src.bluesky_taskgraph_runner.core.types import PlanArgs, PlanOutput


def read_device(device: Device):
    return device.read()[device.name]["value"]


class ConditionalTask(BlueskyTask):
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

    def __init__(self, name: str, first_task: BlueskyTask,
                 second_task: BlueskyTask = None):
        super().__init__(name)
        self._first_task: BlueskyTask = first_task
        self._second_task: BlueskyTask = second_task \
            or BlueskyTask(f"{first_task.name} skipped!")

    """
    Override me
    """

    def _check_condition(self, condition_check_args: PlanArgs) -> bool:
        ...

    def propagate_status(self, status: TaskStatus) -> None:
        self._overwrite_results(status.obj.results)
        super().propagate_status(status)

    def _run_task(self, *args: PlanArgs) -> PlanOutput:
        condition = self._check_condition(*args)
        task = self._first_task if condition else self._second_task
        self._logger.info(
            f"Condition was {condition}: running {task.name} with args {args}")
        # Track the state of the plan we choose to run
        task.add_complete_callback(self.propagate_status)
        yield from task.execute(*args)


class TransparentTask(BlueskyTask):
    """
    Task that returns all its inputs in the same order as outputs.
      e.g. an iterative function that searches for a better match, but if the initial
      inputs are close enough can be wrapped by a ConditionalTask and return those.
    Since outputs can be truncated by requesting a shorter list of output names, this
    may have some use passed as second_task to a ConditionalTask
    """

    def _run_task(self, *args: PlanArgs) -> PlanOutput:
        self._results = args
        yield from BlueskyTask._run_task(self)
