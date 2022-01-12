import logging
from typing import Tuple, Iterator, List, Any, Optional, Callable, Dict

from bluesky import RunEngine, Msg
from bluesky.run_engine import default_scan_id_source
from bluesky.suspenders import SuspendCeil
from ophyd import Signal

from src.bluesky_taskgraph_runner.core.task import DecisionEngineKnownException, TaskFail, TaskStatus, BlueskyTask
from src.bluesky_taskgraph_runner.core.task_graph import TaskGraph
from src.bluesky_taskgraph_runner.core.types import Variables, PlanOutput

logger = logging.getLogger("task")


# TODO: More informative logging name?


class DecisionEngineRunEngine(RunEngine):
    """
    An extension to the RunEngine to allow the TaskCallback function which maps the Status of a group (e.g. a long
    running move) to the task that created it
    """

    def __init__(self, md=None, *, loop=None, preprocessors=None, context_managers=None, md_validator=None,
                 scan_id_source=default_scan_id_source, during_task=None):
        super().__init__(md, loop=loop, preprocessors=preprocessors, context_managers=context_managers,
                         md_validator=md_validator, scan_id_source=scan_id_source, during_task=during_task)
        self.register_command("TaskCallback", self._task_callback)

    async def _task_callback(self, msg: Msg) -> None:
        task = msg.obj
        statuses = list(self._status_objs.get(msg.kwargs["group"]))
        # TODO: What if we expect a callback but don't get one?
        if statuses:
            and_status = statuses[0]
            for _ in range(1, len(statuses)):
                and_status &= statuses[_]
            # It is the responsibility of the status of the Task to know what this callback does, e.g. collects
            #  multiple statuses
            and_status.add_callback(task.propagate_status)


# TODO: Understand what this needs to do and how to do it
# TODO: Possibility of multiple ControlObjects, should ones exceptions stop another?
# TODO: Allow disconnection/passing of control
class DecisionEngineControlObject(SuspendCeil):
    """
    An object that controls the production and submission of decision_engine_plans
    e.g. An object that polls an external service for recipes, conditionally constructs plans and submits them to the
    run engine.
    e.g. holds a timer for when the robot arm needs to be chilled and constructs the next plan to be run with that graph
    As graphs can be composed by all_tasks = tasks + more_tasks, or all_tasks = tasks.depends_on(more_tasks)
    e.g. counts/clears exceptions to pause/resume the RE automatically on exception accumulation
    e.g. can be called to pause and resume the RE as desired
    Extends bluesky.suspenders.SuspenderBase and installs itself as a suspender on the RunEngine to allow it to pause,
    resume and otherwise control the device programmatically by monitoring the signal of the number of exceptions.
    Can hold a subset of all devices/beamline configuration that are required for executing Tasks, to prevent everything
    being available in the namespace
    """

    def __init__(self, run_engine: RunEngine, known_values: Dict[str, Any] = None, suspend_thresh=3, *,
                 resume_thresh=None, **kwargs):
        super().__init__(Signal(name="Decision Engine Exceptions"), suspend_thresh, resume_thresh=resume_thresh,
                         **kwargs)
        self._run_engine = run_engine
        self._known_values = known_values or {}
        self._run_engine.install_suspender(self)
        self._should_stop_at_end_of_next_run = False
        self._error_tasks = {}
        self._recovered_tasks = set()

    # TODO: Track by Task or by ExceptionType or... ?
    def handle_exception(self, task_name: str, exception: Exception) -> None:
        if not exception:
            return self.handle_success(task_name)
        # If we have not anticipated this error, it is a TaskFail
        if not isinstance(exception, DecisionEngineKnownException):
            exception = TaskFail()
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
        self._sig.set(max([v for _, v in self._error_tasks.items()] or [0]))
        self._run_engine.abort("Exception thrown from task")
        if self.tripped:
            self._run_engine.request_pause()

    def clear_signal(self, task_name: Optional[str]) -> None:
        if not task_name:
            self._error_tasks.clear()
            self._recovered_tasks.clear()
        else:
            self._error_tasks.pop(task_name)
        self._set_signal_most_exceptions()

    def do_things(self) -> None:
        while True:
            if self._should_stop_at_end_of_next_run:
                self._run_engine.request_pause(True)
            else:
                self._run_engine(self.decision_engine_plan(self._create_next_graph(), self._known_values))

    # TODO: neaten up comment
    def _create_next_graph(self, overrides: Dict[str, Any] = None) -> TaskGraph:
        """
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

    def decision_engine_plan(self, task_graph: TaskGraph, variables: Variables = None) -> PlanOutput:
        yield from decision_engine_plan(task_graph, variables or self._known_values, self.handle_exception)

    # TODO: Move the run engine loop to another thread so this can be called whenever
    def _pause_run_engine(self, defer=False) -> None:
        self._run_engine.request_pause(defer)

    def _resume_run_engine(self) -> None:
        self._run_engine.resume()

    def _clear_exceptions(self, task_name: Optional[str]) -> None:
        if task_name is None:  # Clear all signals
            self._error_tasks = {}
            self._recovered_tasks = set()
        else:
            self._error_tasks.pop(task_name)

    def add_value(self, name: str, value: Any):
        self.add_values({name: value})

    def add_values(self, dictionary: Dict[str, Any]):
        self._known_values.update(dictionary)

    def remove_value(self, obj: Any):
        if obj in self._known_values.values():
            self._known_values = {key: value for key, value in self._known_values.items() if value != obj}
        else:
            self._known_values = {key: value for key, value in self._known_values.items() if key != obj}

    def __getitem__(self, item):
        return self._known_values[item]

    def __setitem__(self, key, value):
        return self._known_values.__setitem__(key, value)


# TODO: Allow DE to be paused after current task?
# TODO: Can we make Readable to output state of all devices at various points?
# RE already allows us to pause after the current instruction, and we can have checkpoints at tasks as required for
#   rewinding... but this is the VMXi behaviour and we may want to expose here also
# TODO: Validate TaskGraph + variables? TaskGraph inputs must either be outputs or variables
class DecisionEngine:
    """
    The DecisionEngine holds a TaskGraph and map of values gathered from other sources, which may be overridden by
    outputs of tasks. Providing arguments to the Tasks in the TaskGraph as required from this map
    """

    def __init__(self, task_graph: TaskGraph, variables: Variables,
                 exception_tracking_callback: Optional[Callable[[str, Optional[Exception]], None]]):
        self._task_graph = task_graph
        self._variables = dict(variables)
        self.validate()
        # TODO: better way to prevent Task: [None] being an issue
        self._completed_tasks = {None}
        self.started_tasks = set()
        self._failed_tasks = set()
        self._exception_tracking_callback = exception_tracking_callback
        for task in self._task_graph.graph.keys():
            task.add_complete_callback(self.finish_task)

    """
    Callback function to be passed to a Task for it to report back to the DecisionEngine when it is complete, rather
    than requiring the DecisionEngine to check its state.
    """

    def finish_task(self, status: TaskStatus) -> None:
        task = status.obj
        if status.success:
            # Ensure we add any outputs before letting tasks that depend on this begin
            self._variables.update(task.get_results(self._task_graph.outputs.get(task, [])))
            self._completed_tasks.add(task)
            # TODO: Exception when tasks finish too quickly
            self._exception_tracking_callback(task.name, None)
        else:
            # Task is finished so no timeout necessary
            exc = status.exception(None)
            logger.warning(f"Task {task}", exc_info=exc)
            if self._exception_tracking_callback:
                self._exception_tracking_callback(task.name(), exc)
            self._failed_tasks.add(task)

    # TODO: How to handle failure of tasks
    def is_complete(self) -> bool:
        return (len(self._failed_tasks) or
                all([t.complete() for t in self._task_graph.graph.keys()]))

    def give_valid_tasks(self) -> Iterator[Tuple[BlueskyTask, List[Any]]]:
        # TODO: iter?
        # Start any pending task that has its dependencies fulfilled
        tasks = [t for t in self._task_graph.graph.keys() if not (t.started() or t in self.started_tasks)
                 and self._task_graph.graph[t].issubset(self._completed_tasks)]
        task_inputs = [[self._variables.get(a, None) for a in self._task_graph.inputs.get(t, [])] for t in tasks]

        return zip(tasks, task_inputs)

    # TODO: Improve, handle case of outputs that are only available after input
    # TODO: Optional args
    def validate(self) -> None:
        known_values = [value for _, values in self._task_graph.outputs.items() for value in values] \
                       + list(self._variables.keys())
        needed_values = [value for _, values in self._task_graph.inputs.items() for value in values]
        unknown_values = [value for value in needed_values if value not in known_values]
        if unknown_values:
            raise Exception(f"Unknown values! {unknown_values}")


def decision_engine_plan(task_graph: TaskGraph,
                         variables: Variables = None,
                         exception_handling: Optional[Callable[[str, Exception], None]] = None) -> PlanOutput:
    if not variables:
        variables = {}
    decision_engine = DecisionEngine(task_graph, variables, exception_handling)
    while not decision_engine.is_complete():
        for (task, args) in decision_engine.give_valid_tasks():
            decision_engine.started_tasks.add(task)
            yield from task.execute(args)
