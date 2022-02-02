from typing import Dict, Any, List, Optional, Generator, Callable

from bluesky import Msg
from bluesky.protocols import Status

BlueskyTask = "src.bluesky_taskgraph_runner.core.task.BlueskyTask"

Graph = Dict[BlueskyTask, List[BlueskyTask]]
Input = Dict[BlueskyTask, List[str]]
Output = Dict[BlueskyTask, List[str]]

Variables = Dict[str, Any]
PlanArgs = Optional[List[Any]]
KwArgs = Optional[Dict[str, Any]]

PlanOutput = Generator[Msg, None, None or Status]
PlanCallable = Callable[[Optional[PlanArgs], Optional[KwArgs]], PlanOutput]
