import uuid
from typing import Optional, Dict, Any, List

from bluesky import Msg
from bluesky.plan_stubs import sleep, wait, abs_set, stage, create, read, save
from ophyd import Device

from src.bluesky_taskgraph_runner.core.task import BlueskyTask
from src.bluesky_taskgraph_runner.core.types import PlanOutput


# TODO: Are these useful? Tasks should be larger than plan stubs, should be a chunk of behaviour.
#  e.g. not abs_set(device, location) but "Move devices out of beam"
from src.bluesky_taskgraph_runner.tasks.behavioural_tasks import read_device
from src.bluesky_taskgraph_runner.tasks.functional_tasks import DeviceCallbackTask, DeviceTask


class OpenRunTask(BlueskyTask):
    """
    Task to open a Bluesky run: the run_id can either be set when it should be human readable and is known during task
    construction or else is randomly generated- in either case it is available as a property for use creating the
    matching CloseRunTask, and as an output for tasks that wish to use the run_id
    execute args:
        md: dictionary of metadata to associate with the run in the RunEngine
    results:
        the id of the run
    See Also
    --------
    :func:`bluesky.plan_stubs.open_run`
    """

    def __init__(self, run_id: uuid.UUID = None, name: str = None):
        if not run_id:
            run_id = uuid.uuid4()
        super().__init__(name or f"Open Run {run_id} Task")
        self._run_id = run_id

    @property
    def run_id(self):
        return self._run_id

    def _run_task(self, md: Optional[Dict[str, Any]] = None) -> PlanOutput:
        # We want to be able to return the run id so we can close it later, so we cannot use the plan stub
        yield Msg('open_run', None, run=self._run_id, **(md or {}))
        self._results = [self._run_id]
        yield from BlueskyTask._run_task(self)


class CloseRunTask(BlueskyTask):
    """
    Task to close a Bluesky run: exit_status and reason are optional.
    Default case: exit_status = None, reason = None and the values are taken from the RunEngine- these should only be
    overridden if the task knows something the RunEngine doesn't: e.g. results of external processing
    execute args:
        exit_status: {None, 'success', 'abort', 'fail'} the final status of the run
        reason: a long form string explaining the exit_status
    results:
        the id of the run
    See Also
    --------
    :func:`bluesky.plan_stubs.close_run`
    """

    def __init__(self, run_id: uuid.UUID, name: str = None):
        super().__init__(name or f"Close Run {run_id} Task")
        self._run_id = run_id

    def _run_task(self, exit_status: Optional[str] = None, reason: Optional[str] = None) -> PlanOutput:
        # We need to know the run we close (we may need to open and close several plans within a task!)
        yield Msg('close_run', None, run=self._run_id, exit_status=exit_status, reason=reason)
        self._results = [self._run_id]
        yield from BlueskyTask._run_task(self)


class SleepTask(BlueskyTask):
    """
    Task to request a sleep on the current plan without interrupting the RunEngine's processing of interrupts etc.
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
    Task to request the RunEngine waits until all statuses associated with a group have finished before continuing to
    the next task, using the status of the group as the status of completion of the task. e.g. a finished move or a
    failed kickoff will propagate its status up to this task, in turn propagating to the DecisionEngine
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
        if group:
            # The wait is a success if whatever we were waiting for was a success
            yield Msg('TaskCallback', obj=self, group=group)
        else:
            yield from BlueskyTask._run_task(self)


class SetTask(DeviceCallbackTask):
    """
    Task to request the RunEngine set a Movable to a value, completes when the move is completed. Can be added to a
    group if required, otherwise a group is constructed from the name of this task, so these tasks should be usefully
    named
    execute args:
        device: a Movable
        value: a value that the Movable can be set to.
        group: an optional name for the group that tracks the movement, else assumed to be in a group of just this task
    result:
        value of the Movable before it is requested to move
        value of the Movable after reporting its status is finished
    See Also
    --------
    :func:`bluesky.plan_stubs.set`
    """

    def _run_task(self, device: Device, value: Any, group: Optional[str] = None) -> PlanOutput:
        self.add_result(read_device(device))
        yield from abs_set(device, value, group=group or self.name())
        # The wait is a success if the set was a success
        yield from self._track_device_status(group)


class SetDeviceTask(DeviceTask):

    def _run_task(self, value: Any, group: Optional[str] = None) -> PlanOutput:
        self.add_result(read_device(self._device))
        yield from abs_set(self._device, value, group=group or self.name())
        yield from self._track_device_status(group)


class SetKnownValueDeviceTask(DeviceTask):
    def __init__(self, name: str, device: Device, value: Any):
        super().__init__(name, device)
        self._value = value

    def _run_task(self, group: Optional[str]) -> PlanOutput:
        self.add_result(read_device(self._device))
        yield from abs_set(self._device, self._value, group=group or self.name())
        yield from self._track_device_status(group)


class StageTask(BlueskyTask):
    """
    Task to stage a device
    See Also
    --------
    :func:`bluesky.plan_stubs.stage`
    """

    def _run_task(self, device: Device) -> PlanOutput:
        yield from stage(device)
        # TODO: Can we get a callback for the staging of this device?
        #  Or else, is this blocking until the device is staged?
        yield from BlueskyTask._run_task(self)


class StageDeviceTask(DeviceTask):

    def _run_task(self) -> PlanOutput:
        yield from stage(self._device)
        # TODO: as above
        yield from BlueskyTask._run_task(self)


class ReadDevicesAndEmitEventDocument(BlueskyTask):
    """
    Task to request the RunEngine read all devices into a document, then emit it in a given stream,
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
            yield from read(device)
        yield from save()
        yield from BlueskyTask._run_task(self)
