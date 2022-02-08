from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from bluesky.plan_stubs import (
    abs_set,
    close_run,
    create,
    open_run,
    read,
    save,
    sleep,
    stage,
    wait,
)
from bluesky.protocols import Status
from ophyd import Device

from python_bluesky_taskgraph.core.task import BlueskyTask
from python_bluesky_taskgraph.core.types import (
    EmptyInput,
    GroupArg,
    Input,
    KwArgs,
    SetInputs,
    TaskOutput,
)
from python_bluesky_taskgraph.tasks.behavioural_tasks import read_device
from python_bluesky_taskgraph.tasks.functional_tasks import DeviceCallbackTask, Devices


# TODO: Are these useful? Tasks should be larger than plan stubs,
#  should be a chunk of behaviour.
#  e.g. not abs_set(device, location) but "Move devices out of beam"
class OpenRunTask(BlueskyTask[KwArgs]):
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

    def organise_inputs(self, *args) -> KwArgs:
        return KwArgs(*args)

    def _run_task(self, metadata: KwArgs) -> TaskOutput:
        run_id = yield from open_run(**metadata.kwargs)
        self.add_result(run_id)
        yield from self._add_callback_or_complete(None)


class CloseRunTask(BlueskyTask["CloseRunTask.CloseRun"]):
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

    @dataclass
    class CloseRun(Input):
        exit_status: Optional[str] = None
        reason: Optional[str] = None

    def __init__(self):
        super().__init__("Close Run Task")

    def organise_inputs(self, *args) -> CloseRun:
        return CloseRunTask.CloseRun(*args)

    def _run_task(self, run_close_args: CloseRun) -> TaskOutput:
        run_id = yield from close_run(run_close_args.exit_status, run_close_args.reason)
        self.add_result(run_id)
        yield from self._add_callback_or_complete(None)


class SleepTask(BlueskyTask["SleepTask.SleepArgs"]):
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

    @dataclass
    class SleepArgs(Input):
        sleep_time: Optional[float] = None

    def __init__(self, name: str, sleep_time: Optional[float] = None):
        super().__init__(name)
        self.sleep_time = sleep_time or 1

    def organise_inputs(self, *args) -> SleepArgs:
        return SleepTask.SleepArgs(*args)

    def _run_task(self, sleep_time: SleepArgs) -> TaskOutput:
        ret = yield from sleep(sleep_time.sleep_time or self.sleep_time)
        yield from self._add_callback_or_complete(ret)


class WaitTask(BlueskyTask[GroupArg]):
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

    def organise_inputs(self, *args) -> GroupArg:
        return GroupArg(*args)

    def _run_task(self, group: GroupArg) -> TaskOutput:
        ret = yield from wait(group=group.group)
        yield from self._add_callback_or_complete(ret)


class SetDeviceTask(BlueskyTask[SetInputs]):
    def __init__(self, device: Device, name: str):
        super().__init__(name)
        self._device = device

    def _run_task(self, inputs: SetInputs) -> TaskOutput:
        self.add_result(read_device(self._device))
        ret: Optional[Status] = yield from abs_set(
            self._device,
            inputs.value,
            group=inputs.group or self.name,
            **inputs.kwargs or {}
        )
        self.add_result(read_device(self._device))
        yield from self._add_callback_or_complete(ret)

    def organise_inputs(self, *args: Any) -> SetInputs:
        return SetInputs(*args)


class SetTask(DeviceCallbackTask["SetTask.SetDeviceInputs"]):
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

    @dataclass
    class SetDeviceInputs(Input):
        device: Device
        value: Any
        group: Optional[str] = field(default=None)
        kwargs: Dict[str, Any] = field(default_factory=dict)

    def organise_inputs(self, *args) -> SetDeviceInputs:
        return SetTask.SetDeviceInputs(*args)

    def _run_task(self, inputs: SetDeviceInputs) -> TaskOutput:
        self.add_result(read_device(inputs.device))
        ret: Optional[Status] = yield from abs_set(
            inputs.device,
            inputs.value,
            group=inputs.group or self.name,
            **inputs.kwargs
        )
        yield from self._add_callback_or_complete(ret)


class SetKnownValueDeviceTask(BlueskyTask["SetKnownValueDeviceTask.SetKnownInputs"]):
    @dataclass
    class SetKnownInputs(Input):
        group: Optional[str] = field(default=None)
        kwargs: Dict[str, Any] = field(default_factory=dict)

    def __init__(self, name: str, device: Device, value: Any):
        super().__init__(name)
        self._device = device
        self._value = value

    def organise_inputs(self, *args) -> SetKnownInputs:
        return SetKnownValueDeviceTask.SetKnownInputs(*args)

    def _run_task(self, inputs: SetKnownInputs) -> TaskOutput:
        self.add_result(read_device(self._device))
        ret: Optional[Status] = yield from abs_set(
            self._device, self._value, inputs.group or self.name, **inputs.kwargs
        )
        yield from self._add_callback_or_complete(ret)


class StageTask(BlueskyTask["StageTask.DeviceInput"]):
    """
    Task to stage a device
    See Also
    --------
    :func:`bluesky.plan_stubs.stage`
    """

    @dataclass
    class DeviceInput(Input):
        device: Device

    def organise_inputs(self, *args) -> DeviceInput:
        return StageTask.DeviceInput(*args)

    def _run_task(self, inputs: DeviceInput) -> TaskOutput:
        list_of_staged_devices = yield from stage(inputs.device)
        self._overwrite_results(list_of_staged_devices)
        # TODO: Can we get a callback for the staging of this device?
        #  Or else, is this blocking until the device is staged?
        yield from self._add_callback_or_complete(None)


class StageDevicesTask(BlueskyTask[EmptyInput]):
    def __init__(self, device: Device, name: str):
        super().__init__(name)
        self._device = device

    def organise_inputs(self, *args: Any) -> EmptyInput:
        return EmptyInput()

    def _run_task(self, inputs: EmptyInput) -> TaskOutput:
        list_of_stages_devices = yield from stage(self._device)
        self._overwrite_results(list_of_stages_devices)
        # TODO: as above
        yield from self._add_callback_or_complete(None)


class ReadDevicesAndEmitEventDocument(
    BlueskyTask["ReadDevicesAndEmitEventDocument.DevicesAndStreamName"]
):
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

    @dataclass
    class DevicesAndStreamName(Devices):
        stream_name: str

    def organise_inputs(self, *args) -> DevicesAndStreamName:
        return ReadDevicesAndEmitEventDocument.DevicesAndStreamName(*args)

    def _run_task(self, inputs: DevicesAndStreamName) -> TaskOutput:
        name = inputs.stream_name or "Primary"
        yield from create(name)
        for device in inputs.devices:
            yield from read(device)  # Read returns a dictionary, not a Status
        yield from save()
        yield from self._add_callback_or_complete(None)
