from typing import Dict, Any, List, Iterable, Optional

from bluesky import Msg

Graph = Dict['BlueskyTask', List['BlueskyTask']]
Input = Dict['BlueskyTask', List[str]]
Output = Dict['BlueskyTask', List[str]]
PlanOutput = Iterable[Msg]
Variables = Dict[str, Any]
PlanArgs = Optional[List[Any]]
KwArgs = Optional[Dict[str, Any]]
