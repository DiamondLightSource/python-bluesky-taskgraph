from bluesky import Msg

from src.bluesky_taskgraph_runner.core.task import BlueskyTask
from src.bluesky_taskgraph_runner.core.types import PlanOutput


def task_callback(task: BlueskyTask, group: str = None) -> PlanOutput:
    yield Msg('TaskCallback', obj=task, group=group or task.name())
