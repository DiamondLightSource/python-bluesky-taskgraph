from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional

from bluesky import Msg
from bluesky.plan_stubs import create, read, save
from bluesky.protocols import Status
from ophyd import DeviceStatus

from python_bluesky_taskgraph.core.task import BlueskyTask
from python_bluesky_taskgraph.core.types import Devices, Input, InputType, TaskOutput
from python_bluesky_taskgraph.tasks.behavioural_tasks import read_device


class DeviceCallbackTask(BlueskyTask[InputType], ABC):
    """
    Utility Task to define a task that waits for a Device to finish and adds its final
    value as a result
    """

    def propagate_status(self, status: Status) -> None:
        super().propagate_status(status)
        if isinstance(status, DeviceStatus):
            # status.device is Movable, so must be Readable
            # TODO: Need to extract the actual ax[is/es] we need...
            self.add_result(read_device(status.device))
        # TODO: What do we get if it's not DeviceStatus and is it ever going to be not
        #  DeviceStatus?


class ReadBeamlineState(BlueskyTask[Devices]):
    """
    TODO: Is this the right way to do this?
    Task that
     emits an EventDescriptorDocument on the "beamline-state" stream then
     reads all devices and emits an EventDocument in the same stream
    So we can track the beamline state over multiple tasks/runs
    """

    def __init__(self):
        super().__init__("Reading Beamline state")

    def organise_inputs(self, *args) -> Devices:
        return Devices(*args)

    def _run_task(self, devices: Devices) -> TaskOutput:
        yield from create(name="beamline_state")
        for device in devices.devices:
            yield from read(device)
        yield from save()
        yield from self._add_callback_or_complete(None)


class PlanTask(BlueskyTask["PlanTask.PlanInputs"]):
    """
    TODO: Is there a better way to do this kind of task?
    Task that yields all instructions from a pre-existing plan or plan stub.
    Any non-kwargs should be passed as a list to the kwargs map with name "args"
    TODO: Is there a better way to do this passing of args?
    Should be called with a dictionary of str (argument name) to any (argument) as
    appropriate for the Plan, without any unknown method args.
    """

    @dataclass
    class PlanInputs(Input):
        args: List[Any]
        kwargs: Dict[str, Any] = field(default_factory=dict)

    Plan = Callable[..., Generator[Msg, None, Optional[Status]]]

    def __init__(self, name: str, plan: Plan):
        super().__init__(name)
        self._plan = plan

    def organise_inputs(self, *args) -> PlanInputs:
        return PlanTask.PlanInputs(*args)

    def _run_task(self, inputs: PlanInputs) -> TaskOutput:
        args = inputs.args or []
        kwargs = inputs.kwargs
        ret: Optional[Status] = yield from self._plan(*args, **kwargs)
        # If the Plan returns a Status, we watch it, else we can only presume we are
        #  done
        yield from self._add_callback_or_complete(ret)
