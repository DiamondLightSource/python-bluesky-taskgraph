from dataclasses import dataclass
from typing import Callable, Dict, List, Set, Union

from python_bluesky_taskgraph.core.task import BlueskyTask
from python_bluesky_taskgraph.tasks.stub_tasks import CloseRunTask, OpenRunTask


@dataclass
class TaskTuple:
    task: BlueskyTask
    inputs: List[str]
    outputs: List[str]


Graph = Dict[BlueskyTask, Set[BlueskyTask]]
GraphInput = Dict[BlueskyTask, List[str]]
GraphOutput = Dict[BlueskyTask, List[str]]
TaskOrGraph = Union[BlueskyTask, "TaskGraph", TaskTuple]


def _format_task(
        task: BlueskyTask,
        dependencies: Set[str],
        inputs: List[str],
        outputs: List[str],
):
    return (
        f"{task.name}: depends on: {dependencies}, "
        f"has inputs: {inputs}, has outputs: {outputs}"
    )


# TODO: Likely other useful inbuilt methods to override
class TaskGraph:
    """
    A TaskGraph contains a mapping of task to all of the tasks that must be complete
    before it starts (the graph), as well as a mapping of task to the *names* of
    inputs that it will receive and *names* of outputs that it will provide
    This mapping is done by the TaskGraph to prevent accidental shadowing by outputs:
      e.g. a device named "wavelength" and a value named the same provided by another
      task.
    """

    def __init__(self, task_graph: Graph, inputs: GraphInput, outputs: GraphOutput):
        self.graph = {k: set(v) for k, v in task_graph.items() if k}
        self.inputs = dict(inputs)
        self.outputs = dict(outputs)

    def __add__(self, other: TaskOrGraph) -> "TaskGraph":
        if isinstance(other, TaskGraph):
            return TaskGraph(
                {**self.graph, **other.graph},
                {**self.inputs, **other.inputs},
                {**self.outputs, **other.outputs},
            )
        if isinstance(other, BlueskyTask):
            return self.__add__(TaskTuple(other, [], []))
        if isinstance(other, TaskTuple):
            return self.__add__(
                TaskGraph(
                    {other.task: set()},
                    {other.task: other.inputs},
                    {other.task: other.outputs},
                )
            )

    def __radd__(self, other: TaskOrGraph) -> "TaskGraph":
        return self.__add__(other)

    def __str__(self) -> str:
        tasks = self.graph.keys()
        dependencies = (
            {dependency.name for dependency in self.graph.get(key, [])} for key in tasks
        )
        inputs = (self.inputs.get(key, []) for key in tasks)
        outputs = (self.outputs.get(key, []) for key in tasks)
        return str(
            [_format_task(*task) for task in zip(tasks, dependencies, inputs, outputs)]
        )

    def __len__(self) -> int:
        return len(self.graph)

    """
    Makes all tasks in this graph depend on the completion of all tasks within
    another graph
    And adds the other graph to this graph.
    Returns the combined graph to allow chaining of this method
    """

    def depends_on(self, other: TaskOrGraph) -> "TaskGraph":
        if isinstance(other, BlueskyTask):
            other = TaskTuple(other, [], [])
        new_dependencies = (
            set(other.graph.keys()) if isinstance(other, TaskGraph) else {other.task}
        )
        for _, dependencies in self.graph.items():
            dependencies.update(new_dependencies)
        return self + other

    """
    Makes all tasks in another graph depend on the completion of all tasks within
    this graph
    And adds this graph to the other graph.
    Returns the combined graph to allow chaining of this method
    """

    def is_depended_on_by(self, other: TaskOrGraph) -> "TaskGraph":
        if isinstance(other, BlueskyTask):
            return self.is_depended_on_by(TaskGraph.from_task(other))
        if isinstance(other, TaskTuple):
            return self.is_depended_on_by(TaskGraph.from_task_tuple(other))
        return other.depends_on(self)

    @staticmethod
    def from_task(task: BlueskyTask):
        return TaskGraph({task: set()}, {}, {})

    @staticmethod
    def from_task_tuple(task_tuple: TaskTuple):
        return TaskGraph(
            {task_tuple.task: set()},
            {task_tuple.task: task_tuple.outputs},
            {task_tuple.task: task_tuple.inputs},
        )


def taskgraph_run_decorator(func: Callable[..., TaskGraph]) -> Callable[..., TaskGraph]:
    def wrapper_run_decorator(*args, **kwargs) -> TaskGraph:
        decorated_taskgraph = (
            func(*args, **kwargs)
                .is_depended_on_by(CloseRunTask())
                .depends_on(OpenRunTask())
        )
        return decorated_taskgraph

    return wrapper_run_decorator
