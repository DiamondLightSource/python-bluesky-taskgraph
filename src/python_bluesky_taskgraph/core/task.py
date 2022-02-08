import logging
from abc import abstractmethod
from time import time
from typing import Any, Callable, Dict, Generator, Generic, List, Optional

from bluesky import Msg
from ophyd.status import Status

from python_bluesky_taskgraph.core.types import InputType


class DecisionEngineKnownException(Exception):
    def __init__(self, fatal=True):
        self._is_fatal = fatal

    @property
    def is_fatal(self) -> bool:
        return self._is_fatal


class TaskStop(DecisionEngineKnownException):
    def __init__(self):
        super().__init__(False)


class TaskFail(DecisionEngineKnownException):
    def __init__(self):
        super().__init__(True)


class BlueskyTask(Generic[InputType]):
    """
    A Task to be run by Bluesky.
    Tasks are intended to be generic, but are required to have a name, which is
    recommended to be unique and human readable, to enable debugging of the TaskGraph
    they are a part of. Tasks should have their arguments passed via the TaskGraph.
      Although If they are available when the Tasks are constructed they may be
      passed directly.
    Tasks are not expected to track or know the names of the inputs they are taking,
    only their type and order.
      e.g. task_run may have a signature(Device, Value) and moves the Device to the
      Value. The Device and Value passed are either decided at construction time of
      the task or passed from the DecisionEngine: as the DecisionEngine could have
      several tasks that output Devices, none of which can guarantee unique naming, the
      TaskGraph creator/decision engine is expected to know which exact Device
      should be passed.
    """

    def __init__(self, name: str):
        self._name: str = name
        # TODO: Do we want logging at the Task, DecisionEngine or ControlObject level?
        self._logger = logging.getLogger("BlueskyTask")
        self._results: List[Any] = []
        self.status: Status = Status(obj=self)

    def __str__(self) -> str:
        if self.complete:
            return f"{self._name} Complete: {self._results}"
        return f"{self._name}: Not Finished"

    """
    Add a callback for the status of this Task to call once the Task is complete:
    whether successful or not.
    This will contain a callback to the DecisionEngine, to allow it to update its Set
    of tasks that have completed
    """

    def add_complete_callback(self, callback: Callable[[Status], None]) -> None:
        self.status.add_callback(callback)

    """
    Propagate the status of another Status into the Status of this Task.
      e.g. is a Task causes a long running movement, its Status should not be
       considered complete until the movement is complete. Tasks that do so should
       therefore propagate the completion of the Status of the long running operation
    Tasks tracking multiple movements, or those with more precise expected statuses may
    wish to override this method
    """

    def propagate_status(self, status: Status) -> None:
        # Status is complete so shouldn't need a timeout?
        exception = status.exception(None)
        if exception:
            self.status.set_exception(exception)
        else:
            self.status.set_finished()

    def _add_callback_or_complete(
        self, status: Optional[Status]
    ) -> Generator[Msg, None, None]:
        if status:
            status.add_callback(self.propagate_status)
        else:
            self._logger.info(f"Task {self.name} presumed finished at {time()}")
            self.status.set_finished()
        yield from ()

    def _fail(self, exc: Optional[Exception] = None) -> None:
        if exc is None:
            exc = TaskStop()
        self.status.set_exception(exc)

    @property
    def name(self) -> str:
        return self._name

    @property
    def complete(self) -> bool:
        return self.status.done

    """
    To track the status of the task for the decision engine, we must create a
    TaskStatus with a callback to the DecisionEngine (handled by the constructor).
    We additionally log that the Task has started.
    We return the Status in case it is helpful to wherever we are being called:
    the decision engine, or else a ConditionalTask, etc.
    """

    def execute(self, args) -> Generator[Msg, None, Status]:
        self._logger.info(f"Task {self.name} begun at {time()}")
        yield from self._run_task(self.organise_inputs(*args))
        return self.status

    @abstractmethod
    def organise_inputs(self, *args: Any) -> InputType:
        ...

    @abstractmethod
    def _run_task(self, inputs: InputType) -> Generator[Msg, None, None]:
        ...

    def add_result(self, result: Any) -> None:
        self._results.append(result)

    def _overwrite_results(self, results: List[Any] = None) -> None:
        if results is None:
            results = []
        self._results = results

    """
    Maps a List of names to the list of results we have.
    Prior results that are not wanted can be ignored by passing None as the argument
      in its position of the list.
    Tail end results that are not wanted can be ignored by passing a list shorter than
      the number of results, as zip truncates the lists
    """

    def get_results(self, keys: List[str]) -> Dict[str, Any]:
        return {k: v for (k, v) in zip(keys, self._results) if k is not None}
