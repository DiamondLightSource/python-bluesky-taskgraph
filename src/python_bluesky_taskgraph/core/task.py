import logging
from abc import abstractmethod
from dataclasses import astuple
from time import time
from typing import Any, Callable, Dict, Generator, Generic, List, Optional

from bluesky import Msg
from bluesky.plan_stubs import stage, unstage
from ophyd import Device
from ophyd.status import Status

from python_bluesky_taskgraph.core.types import InputType, TaskOutput


class DecisionEngineKnownException(Exception):
    def __init__(self, task_name: str, fatal=True):
        self._source: str = task_name
        self._is_fatal: bool = fatal

    @property
    def is_fatal(self) -> bool:
        return self._is_fatal

    @property
    def task_name(self) -> str:
        return self._source


class TaskStop(DecisionEngineKnownException):
    def __init__(self, task_name: str):
        super().__init__(task_name, False)


class TaskFail(DecisionEngineKnownException):
    def __init__(self, task_name: str):
        super().__init__(task_name, True)


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
        self._logger = logging.getLogger(self.name)
        self._results: List[Any] = []
        self.status: Status = Status(obj=self)

    def __str__(self) -> str:
        if self.complete:
            return f"{self.name} Complete: {self._results}"
        return f"{self.name}: Not Finished"

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
        exception: Optional[Exception] = status.exception(None)
        if exception:
            self._logger.error(f"Task {self.name}: Exception! {exception}")
            self.status.set_exception(exception)
        else:
            self._logger.info(f"Task {self.name} finished at {time()}")
            self.status.set_finished()

    # TODO: Handle UUID? Is it wait UUID or scan UUID? Either way, no RunEngine to
    #  wait here...
    def _add_callback_or_complete(self, status: Optional[Status]) -> TaskOutput:
        if status:
            status.add_callback(self.propagate_status)
        else:
            self._logger.info(f"Task {self.name} presumed finished at {time()}")
            self.status.set_finished()
        yield from ()

    def _fail(self, exc: Optional[Exception] = None) -> None:
        if exc is None:
            exc = TaskStop(self.name)
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
        self._logger.info(f"Task {self.name} began at {time()}")
        self._logger.debug(f"Task {self.name} began with args {args}")
        try:
            yield from self._run_task(self.organise_inputs(*args))
        except Exception as e:
            self.status.set_exception(e)
        return self.status

    @abstractmethod
    def organise_inputs(self, *args: Any) -> InputType:
        ...

    @abstractmethod
    def _run_task(self, inputs: InputType) -> TaskOutput:
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


def run_stage_decorator(
    func: Callable[[InputType], TaskOutput]
) -> Callable[[InputType], TaskOutput]:
    def decorated_func(args: InputType):
        devices = {device for device in astuple(args) if isinstance(device, Device)}
        for device in devices:
            yield from stage(device)
        yield from func(args)
        for device in devices:
            yield from unstage(device)

    return decorated_func


def task_stage_decorator(
        func: Callable[..., BlueskyTask[InputType]]
) -> Callable[..., BlueskyTask[InputType]]:
    def wrapper_stage_decorator(*args, **kwargs) -> BlueskyTask[InputType]:
        task: BlueskyTask = func(*args, **kwargs)
        # Prevents MyPy complaints about assigning to a function
        task.__setattr__("_run_task", run_stage_decorator(task._run_task))
        return task

    return wrapper_stage_decorator
