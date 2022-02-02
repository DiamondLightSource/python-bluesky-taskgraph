from typing import Optional, Any, List

from bluesky.plan_stubs import sleep, wait, abs_set, stage, create, read, save, \
    open_run, close_run
from bluesky.protocols import Status
from ophyd import Device

from python_bluesky_taskgraph.core.task import BlueskyTask
from python_bluesky_taskgraph.core.types import PlanOutput, KwArgs
from python_bluesky_taskgraph.tasks.behavioural_tasks import read_device
from python_bluesky_taskgraph.tasks.functional_tasks import DeviceCallbackTask, \
    DeviceTask


# TODO: Are these useful? Tasks should be larger than plan stubs,
#  should be a chunk of behaviour.
#  e.g. not abs_set(device, location) but "Move devices out of beam"
class OpenRunTask(BlueskyTask):
    """
    Task to open a Bluesky run: the run_id is randomly generated and available as a
    result of this task
    execute args:
        md: optional dictionary of metadata to associate with the run in the RunEngine
    results:
        the id of the run
    See Also
    --------
    :func:`bluesky.plan_stubs.open_run`
    """

    def __init__(self):
        super().__init__("Open Run Task")

    def _run_task(self, md: KwArgs = None) -> PlanOutput:
        run_id = yield from open_run(md)
        self.add_result(run_id)
        yield from BlueskyTask._run_task(self)


class CloseRunTask(BlueskyTask):
    """
    Task to close a Bluesky run: exit_status and reason are optional.
    Default case: exit_status = None, reason = None and the values are taken from the
    RunEngine- these should only be overridden if the task knows something the
    RunEngine doesn't: e.g. results of external processing
    execute args:
        exit_status: {None, 'success', 'abort', 'fail'} the final status of the run
        reason: a long form string explaining the exit_status
    results:
        the id of the run
    See Also
    --------
    :func:`bluesky.plan_stubs.close_run`
    """

    def __init__(self):
        super().__init__("Close Run Task")

    def _run_task(self, exit_status: Optional[str] = None, reason: Optional[str] =
    None) -> PlanOutput:
        run_id = yield from close_run(exit_status, reason)
        self.add_result(run_id)
        yield from BlueskyTask._run_task(self)


class SleepTask(BlueskyTask):
    """
    Task to request a sleep on the current plan without interrupting the RunEngine's
    processing of interrupts etc.
    execute args:
        sleep_time: time to wait (in seconds) before continuing the generator.
            Optional: if not set falls back to a constructor arg or 1 second
    result:
        none
    See Also
    --------
    :func:`bluesky.plan_stubs.sleep`
    """

    def __init__(self, name: str, sleep_time: Optional[float] = None):
        super().__init__(name)
        self._sleep_time = sleep_time or 1

    def _run_task(self, sleep_time: Optional[float] = 0) -> PlanOutput:
        yield from sleep(sleep_time or self._sleep_time)
        yield from BlueskyTask._run_task(self)


class WaitTask(BlueskyTask):
    """
    Task to request the RunEngine waits until all statuses associated with a group
    have finished before continuing to the next task
    execute args:
        group: name of a group.
    result:
        none
    See Also
    --------
    :func:`bluesky.plan_stubs.wait`
    """

    def _run_task(self, group: Optional[str] = None) -> PlanOutput:
        yield from wait(group=group)
        yield from BlueskyTask._run_task(self)


class SetTask(DeviceCallbackTask):
    """
    Task to request the RunEngine set a Movable to a value, completes when the move is
    completed. Can be added to a group if required, otherwise a group is constructed
    from the name of this task, so these tasks should be usefully named
    execute args:
        device: a Movable
        value: a value that the Movable can be set to.
        group: an optional name for the group that tracks the movement,
          else assumed to be in a group of just this task
    result:
        value of the Movable before it is requested to move
        value of the Movable after reporting its status is finished
    See Also
    --------
    :func:`bluesky.plan_stubs.set`
    """

    def _run_task(self, device: Device, value: Any, group: Optional[str] = None) \
            -> PlanOutput:
        self.add_result(read_device(device))
        ret: Optional[Status] = yield from abs_set(device, value,
                                                   group=group or self.name())
        if ret:
            ret.add_callback(self.propagate_status)
        else:
            BlueskyTask._run_task(self)


class SetDeviceTask(DeviceTask):

    def _run_task(self, value: Any, group: Optional[str] = None) -> PlanOutput:
        self.add_result(read_device(self._device))
        ret: Optional[Status] = yield from abs_set(self._device, value,
                                                   group=group or self.name())
        if ret:
            ret.add_callback(self.propagate_status)
        else:
            BlueskyTask._run_task(self)


class SetKnownValueDeviceTask(DeviceTask):
    def __init__(self, name: str, device: Device, value: Any):
        super().__init__(name, device)
        self._value = value

    def _run_task(self, group: Optional[str]) -> PlanOutput:
        self.add_result(read_device(self._device))
        ret: Optional[Status] = yield from abs_set(self._device, self._value,
                                                   group=group or self.name())
        if ret:
            ret.add_callback(self.propagate_status)
        else:
            BlueskyTask._run_task(self)


class StageTask(BlueskyTask):
    """
    Task to stage a device
    See Also
    --------
    :func:`bluesky.plan_stubs.stage`
    """

    def _run_task(self, device: Device) -> PlanOutput:
        list_of_staged_devices = yield from stage(device)
        self._overwrite_results(list_of_staged_devices)
        # TODO: Can we get a callback for the staging of this device?
        #  Or else, is this blocking until the device is staged?
        yield from BlueskyTask._run_task(self)


class StageDeviceTask(DeviceTask):

    def _run_task(self) -> PlanOutput:
        list_of_stages_devices = yield from stage(self._device)
        self._overwrite_results(list_of_stages_devices)
        # TODO: as above
        yield from BlueskyTask._run_task(self)


class ReadDevicesAndEmitEventDocument(BlueskyTask):
    """
    Task to request the RunEngine read all devices into a document, then emit it in a
    given stream,
    e.g. "Darks", "Flats", "Primary"
    See Also
    --------
    :func:`bluesky.plan_stubs.create`
    :func:`bluesky.plan_stubs.read`
    :func:`bluesky.plan_stubs.save`
    """

    def _run_task(self, name: str = "primary", *devices: List[Device]) -> PlanOutput:
        yield from create(name)
        for device in devices:
            yield from read(device)  # Read returns a dictionary, not a Status
        yield from save()
        yield from BlueskyTask._run_task(self)
