from typing import Dict, List, Set

from python_bluesky_taskgraph.core.task import BlueskyTask

Graph = Dict[BlueskyTask, Set[BlueskyTask]]
Input = Dict[BlueskyTask, List[str]]
Output = Dict[BlueskyTask, List[str]]


def _format_task(task, dependencies, inputs, outputs):
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

    def __init__(self, task_graph: Graph, inputs: Input, outputs: Output):
        self.graph = {k: set(v) for k, v in task_graph.items() if k}
        self.inputs = dict(inputs)
        self.outputs = dict(outputs)

    def __add__(self, other: "TaskGraph") -> "TaskGraph":
        return TaskGraph(
            {**self.graph, **other.graph},
            {**self.inputs, **other.inputs},
            {**self.outputs, **other.outputs},
        )

    def __radd__(self, other: "TaskGraph") -> "TaskGraph":
        return self.__add__(other)

    def __str__(self) -> str:
        tasks = self.graph.keys()
        dependencies = (
            [dependency.name for dependency in self.graph.get(key, [])] for key in tasks
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

    def depends_on(self, other: "TaskGraph") -> "TaskGraph":
        new_dependencies = set(other.graph.keys())
        for _, dependencies in self.graph.items():
            dependencies.update(new_dependencies)
        return self + other

    """
    Makes all tasks in another graph depend on the completion of all tasks within
    this graph
    And adds this graph to the other graph.
    Returns the combined graph to allow chaining of this method
    """

    def is_depended_on_by(self, other: "TaskGraph") -> "TaskGraph":
        return other.depends_on(self)
