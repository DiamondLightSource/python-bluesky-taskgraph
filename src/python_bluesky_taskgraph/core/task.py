import logging
from time import time
from typing import Callable, Any, Dict, List, Optional, Set

from ophyd.status import Status

from python_bluesky_taskgraph.core.types import PlanArgs, PlanOutput


class TaskStatus(Status):
    """
    Status of a task, automatically adds any callbacks set on the task, and holds the
    Task as its object: to allow the status of the task to automatically call back to
    the DecisionEngine that holds its task, regardless of when the Status[es] it is
    tracking are instantiated
    """

    def __init__(self, task: 'BlueskyTask', timeout=None, settle_time=0, done=None,
                 success=None):
        super().__init__(obj=task, timeout=timeout, settle_time=settle_time, done=done,
                         success=success)
        for callback in task.callbacks():
            self.add_callback(callback)


class DecisionEngineKnownException(Exception):
    def __init__(self, fatal=True):
        self._is_fatal = fatal

    @property
    def is_fatal(self):
        return self._is_fatal


class TaskStop(DecisionEngineKnownException):

    def __init__(self):
        super().__init__(False)


class TaskFail(DecisionEngineKnownException):

    def __init__(self):
        super().__init__(True)


class BlueskyTask:
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
        self._status: Optional[TaskStatus] = None
        self._callbacks: Set[Callable[[TaskStatus], None]] = set()

    def __str__(self) -> str:
        if self.complete:
            return f"{self._name} Complete: {self._results}"
        if self.started:
            return f"{self._name}: Started."
        return f"{self._name}: Not Started"

    """
    Add a callback for the status of this Task to call once the Task is complete:
    whether successful or not.
    This will contain a callback to the DecisionEngine, to allow it to update its Set 
    of tasks that have completed
    """

    def add_complete_callback(self, callback: Callable[[TaskStatus], None]) -> None:
        if self._status:
            self._status.add_callback(callback)
        else:
            self._callbacks.add(callback)

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
            self._status.set_exception(exception)
        else:
            self._status.set_finished()

    def _fail(self, exc: Optional[Exception] = None):
        if self._status is None:
            self._status = TaskStatus(self)
        if exc is None:
            exc = TaskStop()
        self._status.set_exception(exc)

    def name(self) -> str:
        return self._name

    def started(self) -> bool:
        return self._status is not None

    def complete(self) -> bool:
        return self.started() and self._status.done

    def callbacks(self) -> Set[Callable[[TaskStatus], None]]:
        return self._callbacks

    """
    To track the status of the task for the decision engine, we must create a 
    TaskStatus with a callback to the DecisionEngine (handled by the constructor). 
    We additionally log that the Task has started.
    We return the Status in case it is helpful to wherever we are being called:
    the decision engine, or else a ConditionalTask, etc.
    """

    def execute(self, args: PlanArgs) -> PlanOutput:
        self._status = TaskStatus(self)
        self._logger.info(
            msg=f"Task {self.name} started at {time()}, with args: {args}")
        yield from self._run_task(*args)
        return self._status

    """
    The actual commands to be executed by this task.
    This should set the status of the task as finished if this is not updated by a 
    callback from another status
    """

    def _run_task(self, *args: PlanArgs) -> PlanOutput:
        self._logger.info(msg=f"Task {self.name} finished at {time()}")
        self._status.set_finished()
        yield from ()  # Yields from the immutable empty Tuple

    def add_result(self, result: Any) -> None:
        self._results.append(result)

    def _overwrite_results(self, results: Optional[List[Any]] = None) -> None:
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
