import logging
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from bluesky import Msg, RunEngine
from bluesky.suspenders import SuspendCeil, SuspenderBase
from ophyd import Signal
from ophyd.status import Status

from python_bluesky_taskgraph.core.task import (
    BlueskyTask,
    DecisionEngineKnownException,
    TaskFail,
)
from python_bluesky_taskgraph.core.task_graph import TaskGraph

BASE_LOGGER = logging.getLogger(__name__)


def exit_run_engine_on_error_accumulation() -> Generator[Msg, None, None]:
    raise TaskFail("Maximum Exceptions Reached!")


class ExceptionTrackingSuspendCeil(SuspendCeil):
    def __init__(self, suspend_thresh, *, resume_thresh=None, **kwargs):
        self.signal = Signal(name="Exceptions Suspender")
        super().__init__(
            self.signal,
            suspend_thresh,
            resume_thresh=resume_thresh,
            pre_plan=exit_run_engine_on_error_accumulation,
            **kwargs,
        )
        # TODO: Keep the actual exceptions here?
        self._error_tasks: Dict[str, int] = {}
        self._recovered_tasks: Set[str] = set()
        self._logger = BASE_LOGGER.getChild(self.__class__.__name__)

    def handle_exception(
            self, task_name: str, exception: Optional[Exception] = None
    ) -> None:
        """
        Tracks exceptions that accumulate by the name of the task they cause to fail,
        meaning [as with the VMXi case], we can track non-recovering failures and abort
        automatic running if required.
        If called with exception=None, we assume the task_name is in a good state/has
        recovered.
        :param task_name:
        :param exception:
        :return:
        """
        if not exception:
            return self.handle_success(task_name)
        # If we have not anticipated this error, it is a TaskFail
        if not isinstance(exception, DecisionEngineKnownException):
            exception = TaskFail(task_name)
        weighting = 1
        if exception.is_fatal:
            weighting += self._suspend_thresh
        if task_name not in self._error_tasks:
            self._error_tasks[task_name] = weighting
        else:
            self._error_tasks[task_name] = self._error_tasks[task_name] + weighting
            if task_name in self._recovered_tasks:
                self._recovered_tasks.remove(task_name)
        self._set_signal_most_exceptions()

    def handle_success(self, task_name: str) -> None:
        if task_name in self._error_tasks:
            self._error_tasks[task_name] = 0
            self._recovered_tasks.add(task_name)
            self._set_signal_most_exceptions()

    def _set_signal_most_exceptions(self) -> None:
        self._sig.value = max([v for _, v in self._error_tasks.items()] or [0])

    def clear_signal(self, task_name: Optional[str]) -> None:
        if not task_name:
            self._error_tasks.clear()
            self._recovered_tasks.clear()
        else:
            self._error_tasks.pop(task_name)
        self._set_signal_most_exceptions()


class ExceptionTrackingLogger:
    def __init__(self, logger):
        self._logger = logger
        self._error_tasks: Dict[str, int] = {}

    def handle_exception(
            self, task_name: str, exception: Optional[Exception] = None
    ) -> None:
        """
        Tracks exceptions that accumulate by the name of the task they cause to fail,
        meaning [as with the VMXi case], we can track non-recovering failures and abort
        automatic running if required.
        If called with exception=None, we assume the task_name is in a good state/has
        recovered.
        :param task_name:
        :param exception:
        :return:
        """
        if exception:
            if task_name not in self._error_tasks:
                self._error_tasks[task_name] = 1
            self._logger.warn(
                f"{task_name} threw exception {exception}! "
                f"Consecutive errors since this task's last success: "
                f"{self._error_tasks[task_name]}"
            )
        else:
            self.handle_success(task_name)

    def handle_success(self, task_name: str) -> None:
        if task_name in self._error_tasks:
            self._logger.info(
                f"{task_name} recovered! "
                f"Previous consecutive errors: "
                f"{self._error_tasks[task_name]}"
            )
            self._error_tasks[task_name] = 0

    def clear_signal(self, task_name: Optional[str] = None) -> None:
        if not task_name:
            self._error_tasks.clear()
        else:
            self._error_tasks.pop(task_name)


# TODO: Understand what this needs to do and how to do it
# TODO: Allow disconnection/passing of control
# TODO: Should the ControlObject instead be a plan, that constructs
#  DecisionEnginePlans and yields from them?
class DecisionEngineControlObject:
    """
    An object that controls the production and submission of decision_engine_plans
      e.g. An object that polls an external service for recipes, conditionally
        constructs plans and submits them to the run engine.
      e.g. holds a timer for when the robot arm needs to be chilled and constructs the
        next plan to be run with that graph
      e.g. counts/clears exceptions to pause/resume the RE automatically on exception
        accumulation
      e.g. can be called to pause and resume the RE as desired
    Extends bluesky.suspenders.SuspenderBase and installs itself as a suspender on
    the  RunEngine to allow it to pause, resume and otherwise control the device
    programmatically by monitoring the signal of the number of exceptions.
    Can hold a subset of all devices/beamline configuration that are required for
    executing Tasks, to prevent everything being available in the namespace
    """

    def __init__(
            self,
            run_engine: RunEngine,
            known_values: Dict[str, Any] = None,
            *,
            exception_tracker: Optional[ExceptionTrackingSuspendCeil] = None
    ):
        self._run_engine = run_engine
        self._known_values = known_values or {}
        self._error_tasks: Dict[str, int] = {}
        self._recovered_tasks: Set[str] = set()
        self._logger = logging.getLogger(self.__class__.__name__)
        self._exception_tracker: Union[
            ExceptionTrackingLogger, ExceptionTrackingSuspendCeil
        ]
        if exception_tracker:
            self._run_engine.install_suspender(exception_tracker)
            self._exception_tracker = exception_tracker
        else:
            self._exception_tracker = ExceptionTrackingLogger(self._logger)

    def run_task_graphs(self) -> None:
        self._run_engine(self.multiple_task_graphs())

    def multiple_task_graphs(self) -> Generator[Msg, None, None]:
        if isinstance(self._exception_tracker, SuspenderBase):
            while not self._exception_tracker.tripped:
                yield from self.decision_engine_plan(
                    self._create_next_graph(self._known_values)
                )
        else:
            yield from self.decision_engine_plan(
                self._create_next_graph(self._known_values)
            )

    def _create_next_graph(self, overrides: Dict[str, Any] = None) -> TaskGraph:
        """
        Creates the next graph to be run, from conditions known at construction time,
        e.g.
        graph = normal_graph()
        if first_run:
            graph = graph.depends_on(first_run_graph())

        if time > robot_arm_chiller:
            graph = graph.depends_on(create_arm_chiller_graph())

        if simultaneous_process_for_specific_beamline:
            graph += simultaneous_graph()

        return graph
        etc.

        :return: TaskGraph
        """
        ...

    def decision_engine_plan(
        self, task_graph: TaskGraph, variables: Dict[str, Any] = None
    ) -> Generator[Msg, None, Status]:
        ret = yield from decision_engine_plan(
            task_graph,
            variables or self._known_values,
            self._exception_tracker.handle_exception,
        )
        return ret

    def _clear_exceptions(self, task_name: Optional[str]) -> None:
        if task_name is None:  # Clear all signals
            self._error_tasks = {}
            self._recovered_tasks = set()
        else:
            self._error_tasks.pop(task_name)

    def add_value(self, name: str, value: Any) -> None:
        self.add_values({name: value})

    def add_values(self, dictionary: Dict[str, Any]) -> None:
        self._known_values.update(dictionary)

    def remove_value(self, obj: Any) -> None:
        if obj in self._known_values.values():
            self._known_values = {
                key: value for key, value in self._known_values.items() if value != obj
            }
        else:
            self._known_values = {
                key: value for key, value in self._known_values.items() if key != obj
            }

    def __getitem__(self, item) -> Any:
        return self._known_values[item]

    def __setitem__(self, key, value) -> None:
        self._known_values.__setitem__(key, value)


# TODO: Allow DE to be paused after current task?
# TODO: Can we make Readable to output state of all devices at various points?
# RE already allows us to pause after the current instruction, and we can have
# checkpoints at tasks as required for rewinding... but this is the VMXi behaviour
# and we may want to expose here also
class DecisionEngine:
    """
    The DecisionEngine holds a TaskGraph and map of values gathered from other sources,
    which may be overridden by outputs of tasks.
    Arguments are provided to the Tasks as required from this map, and therefore
    dependencies should not only consider hardware constraints but output/input pairs
    """

    def __init__(
        self,
        task_graph: TaskGraph,
        variables: Dict[str, Any],
        exception_tracking_callback: Optional[
            Callable[[str, Optional[Exception]], None]
        ] = None,
    ):
        self._task_graph = task_graph
        self._variables = dict(variables)
        self.validate()
        self._completed_tasks: Set[BlueskyTask] = set()
        self.started_tasks: Set[BlueskyTask] = set()
        self._failed_tasks: Set[str] = set()
        self._exception_tracking_callback = exception_tracking_callback
        for task in self._task_graph.graph.keys():
            task.add_complete_callback(self.finish_task)

    """
    Callback function to be passed to a Task for it to report back to the
    DecisionEngine when it is complete, rather than requiring the DecisionEngine to
    check its state.
    """

    def finish_task(self, status: Status) -> None:
        task = status.obj
        exc = status.exception(None)
        if status.success:
            # Ensure we add any outputs before letting tasks that depend on this begin
            self._variables.update(
                task.get_results(self._task_graph.outputs.get(task, []))
            )
            self._completed_tasks.add(task)
        else:
            # Task is finished so no timeout necessary
            self._failed_tasks.add(task)
        if self._exception_tracking_callback:
            self._exception_tracking_callback(task.name, exc)

    # TODO: How to handle failure of tasks
    @property
    def is_complete(self) -> bool:
        return bool(len(self._failed_tasks)) or all(
            [t.complete for t in self._task_graph.graph.keys()]
        )

    def __iter__(self) -> Iterator[Tuple[BlueskyTask, List[Any]]]:
        # Start any pending task that has its dependencies fulfilled
        tasks = [
            t
            for t in self._task_graph.graph.keys()
            if t not in self.started_tasks
               and self._task_graph.graph[t].issubset(self._completed_tasks)
        ]
        task_inputs = [
            [self._variables.get(a, None) for a in self._task_graph.inputs.get(t, [])]
            for t in tasks
        ]

        return zip(tasks, task_inputs)

    # TODO: Improve, handle case of outputs that are only available after input
    # TODO: Optional args
    def validate(self) -> None:
        known_values = {
            value for _, values in self._task_graph.outputs.items() for value in values
        }
        known_values.update(set(self._variables.keys()))
        needed_values = {
            value for _, values in self._task_graph.inputs.items() for value in values
        }
        unknown_values = {value for value in needed_values if value not in known_values}
        if unknown_values:
            raise Exception(f"Unknown values! {unknown_values}")

    @property
    def status(self) -> Status:
        return Status(done=True) and {
            task.status for task in self._task_graph.graph.keys()
        }


# TODO: Yield a checkpoint after each task?
def decision_engine_plan(
    task_graph: TaskGraph,
    variables: Dict[str, Any] = None,
    exception_handling: Optional[Callable[[str, Optional[Exception]], None]] = None,
) -> Generator[Msg, None, Status]:
    if not variables:
        variables = {}
    decision_engine = DecisionEngine(task_graph, variables, exception_handling)
    while not decision_engine.is_complete:
        for (task, args) in decision_engine:
            decision_engine.started_tasks.add(task)
            try:
                yield from task.execute(args)
            except Exception as e:
                if exception_handling:
                    exception_handling(task.name, e)
                else:
                    raise e
    return decision_engine.status
