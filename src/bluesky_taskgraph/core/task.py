import logging
from abc import abstractmethod
from collections.abc import Callable, Generator
from time import time
from typing import Generic, ParamSpec, TypeVar

from bluesky import Msg
from ophyd.status import Status

BASE_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
P = ParamSpec("P")


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


class Task(Generic[T]):
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
        self._logger = BASE_LOGGER.getChild(self.__class__.__name__).getChild(self.name)
        self._output: T | None = None
        self._status: Status | None = None

    def __str__(self) -> str:
        if self.complete:
            return f"{self.name} Complete: {self._results}"
        return f"{self.name}: Not Finished"

    """
    Add a callback for the status of this Task to call once the Task is complete:
    whether successful or not.
    This will contain a callback to the DecisionEngine, to allow it to update its set
    of tasks that have completed
    """

    def add_complete_callback(self, callback: Callable[[Status], None]) -> None:
        self._status.add_callback(callback)

    """
    Propagate the status of another Status into the Status of this Task.
      e.g. if a Task causes a long running movement, its Status should not be
       considered complete until the movement is complete. Tasks that do so should
       therefore propagate the completion of the Status of the long running operation
    Tasks tracking multiple movements, or those with more precise expected statuses may
    wish to override this method
    """

    def propagate_status(self, status: Status) -> None:
        # Status is complete so shouldn't need a timeout?
        exception: Exception | None = status.exception(None)
        if exception:
            self._logger.error(f"Task {self.name}: Exception! {exception}")
            self._status.set_exception(exception)
        else:
            self._logger.info(f"Task {self.name} finished at {time()}")
            self._status.set_finished()

    def _add_callback_or_complete(self, status: Status | None):
        if status:
            status.add_callback(self.propagate_status)
        else:
            self._logger.info(f"Task {self.name} presumed finished at {time()}")
            self._status.set_finished()

    @property
    def name(self) -> str:
        return self._name

    @property
    def started(self) -> bool:
        return self._status is not None

    @property
    def complete(self) -> bool:
        return self._status is not None and self._status.done

    """
    To track the status of the task for the decision engine, we must create a
    TaskStatus with a callback to the DecisionEngine (handled by the constructor).
    We additionally log that the Task has started.
    We return the Status in case it is helpful to wherever we are being called:
    the decision engine, or else a ConditionalTask, etc.
    """

    def __call__(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> Generator[Msg, None, Status]:
        self.status = Status(obj=self)
        self._logger.info(f"Task {self.name} began at {time()}")
        self._logger.debug(f"Task {self.name} began with args {args}")
        self._output = yield from self.run(*args, **kwargs)
        return self.status

    @abstractmethod
    def run(self, *args: P.args, **kwargs: P.kwargs) -> Generator[Msg, None, T]: ...
