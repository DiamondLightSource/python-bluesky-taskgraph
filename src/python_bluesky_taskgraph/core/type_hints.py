from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from bluesky import Msg
from ophyd import Device

TaskOutput = Generator[Msg, None, None]


@dataclass
class Input: ...


@dataclass
class EmptyInput(Input): ...


T = TypeVar("T")


@dataclass
class TypedInput(Input, Generic[T]):
    obj: T


@dataclass
class KwArgs(Input):
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class GroupArg(Input):
    group: str | None


@dataclass
class Devices(Input):
    devices: list[Device]


@dataclass
class SetInputs(Input):
    group: str
    value: Any
    kwargs: dict[str, Any] = field(default_factory=dict)


InputType = TypeVar("InputType", bound=Input)
