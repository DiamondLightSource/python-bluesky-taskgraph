from abc import abstractmethod
from collections.abc import Callable, Generator

from bluesky import Msg

from bluesky_taskgraph.core.task import P, T, Task


class NoOpTask(Task[None]):
    def _run_task(self) -> Generator[Msg, None, None]:
        yield from self._add_callback_or_complete(None)


class ConditionalTask(Task[T]):
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

    def __init__(
        self,
        name: str,
        conditional: Callable[P, bool],
        first_task: Task[T],
        second_task: Task[T] = None,
    ):
        super().__init__(name)
        self._first_task: Task = first_task
        self._second_task: Task = second_task or NoOpTask(f"{first_task.name} skipped!")
        self._conditional = conditional

    def run(self, *args: P.args, **kwargs: P.kwargs) -> Generator[Msg, None, T]:
        if self._conditional(*args, **kwargs):
            yield from self._second_task(*args, **kwargs)
        else:
            yield from self._first_task(*args, **kwargs)
