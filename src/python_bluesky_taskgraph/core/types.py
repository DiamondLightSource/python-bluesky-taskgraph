from typing import Any, Callable, Dict, Generator, List, Optional

from bluesky import Msg
from bluesky.protocols import Status

BlueskyTask = "python_bluesky_taskgraph.core.task.BlueskyTask"

Graph = Dict[BlueskyTask, List[BlueskyTask]]
Input = Dict[BlueskyTask, List[str]]
Output = Dict[BlueskyTask, List[str]]

Variables = Dict[str, Any]
PlanArgs = Optional[List[Any]]
KwArgs = Optional[Dict[str, Any]]

PlanOutput = Generator[Msg, None, None or Status]
PlanCallable = Callable[[Optional[PlanArgs], Optional[KwArgs]], PlanOutput]
