from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Generic, List, Optional, TypeVar

from bluesky import Msg
from ophyd import Device

TaskOutput = Generator[Msg, None, None]


@dataclass
class Input:
    ...


@dataclass
class EmptyInput(Input):
    ...


T = TypeVar("T")


@dataclass
class TypedInput(Input, Generic[T]):
    obj: T


@dataclass
class KwArgs(Input):
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GroupArg(Input):
    group: Optional[str]


@dataclass
class Devices(Input):
    devices: List[Device]


@dataclass
class SetInputs(Input):
    group: str
    value: Any
    kwargs: Dict[str, Any] = field(default_factory=dict)


InputType = TypeVar("InputType", bound=Input)
