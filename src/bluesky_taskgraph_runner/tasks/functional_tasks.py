from typing import List, Optional

from bluesky.plan_stubs import create, read, save
from bluesky.protocols import Status
from ophyd import DeviceStatus, Device

from src.bluesky_taskgraph_runner.core.task import BlueskyTask
from src.bluesky_taskgraph_runner.core.types import PlanOutput, KwArgs, PlanCallable
from src.bluesky_taskgraph_runner.tasks.behavioural_tasks import read_device


class DeviceCallbackTask(BlueskyTask):
    """
    Utility Task to define a task that waits for a Device to finish moving before considering itself complete
    """

    def propagate_status(self, status: Status):
        super().propagate_status(status)
        if isinstance(status, DeviceStatus):
            # status.device is Movable, so must be Readable
            # TODO: Need to extract the actual ax[is/es] we need...
            self.add_result(read_device(status.device))
        # TODO: What do we get if it's not DeviceStatus and is it ever going to be not DeviceStatus?


class DeviceTask(DeviceCallbackTask):
    """
    Utility Task to define a task instantiated with a device
    """

    def __init__(self, name: str, device: Device):
        super().__init__(name)
        self._device = device


class ReadBeamlineState(BlueskyTask):
    """
    TODO: Is this the right way to do this?
    Task that
     emits an EventDescriptorDocument on the "beamline-state" stream then
     reads all devices and emits an EventDocument in the same stream
    So we can track the beamline state over multiple tasks/runs
    """

    def __init__(self):
        super().__init__("Reading Beamline state")

    def _run_task(self, *devices: List[Device]) -> PlanOutput:
        yield from create(name="beamline_state")
        for device in devices:
            yield from read(device)
        yield from save()
        yield from BlueskyTask._run_task(self)


class PlanTask(BlueskyTask):
    """
    TODO: Is there a better way to do this?
    Task that yields all instructions from a pre-existing plan or plan stub. Any non-kwargs should be passed as a list
    to the kwargs map with name "args" TODO: Is there a better way to do this?
    Should be called with a dictionary of str (argument name) to any (argument) as appropriate for the Plan, without
    any unknown method args.
    """

    def __init__(self, name: str, plan: PlanCallable):
        super().__init__(name)
        self._plan = plan

    def _run_task(self, kwargs: KwArgs = None) -> PlanOutput:
        if kwargs is None:
            kwargs = {}
        ret: Optional[Status] = yield from self._plan(*kwargs.pop("args", []), **kwargs)
        if ret:
            ret.add_callback(self.propagate_status)
        else:
            yield from BlueskyTask._run_task(self)
