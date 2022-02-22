import time
from dataclasses import dataclass
from threading import Thread
from typing import Any, List

from bluesky import RunEngine
from bluesky.plans import grid_scan
from ophyd import Device
from ophyd.sim import SynPeriodicSignal, det1, motor1, motor2
from ophyd.status import Status

from python_bluesky_taskgraph.core.decision_engine import decision_engine_plan
from python_bluesky_taskgraph.core.task import BlueskyTask
from python_bluesky_taskgraph.core.task_graph import TaskGraph
from python_bluesky_taskgraph.core.types import Input, TaskOutput


class RampingMotor(SynPeriodicSignal):
    """
    A device that moves slowly towards a final position once initialised, slow enough
    that concurrent scans can complete in the time it takes to reach a final position
    """

    def ramping_func(self):
        to_return = self.init_value
        self.init_value += self.ramp_value
        return to_return

    def __init__(self, init_value=0, ramp_value=0.1):
        self.init_value = init_value
        self.ramp_value = ramp_value
        super().__init__(
            name="TR6", func=self.ramping_func, period=0.1, period_jitter=0.01
        )


@dataclass
class DeviceParam(Input):
    device: Device


class InitiateRampingTask(BlueskyTask[DeviceParam]):
    def _run_task(self, inputs: DeviceParam) -> TaskOutput:
        inputs.device.start_simulation()
        yield from self._add_callback_or_complete(None)

    def organise_inputs(self, *args: Any) -> DeviceParam:
        return DeviceParam(*args)


class TriggerTask(BlueskyTask[DeviceParam]):
    """
    Sets up a monitoring thread that causes this task to complete [without requiring
    the RunEngine to wait] when the slow moving device reaches a particular value.
    An example of an AsynchronousTask that calls back to the Status of the Task.
    """

    def __init__(self, level: float):
        super().__init__(f"Trigger task, at value {level}")
        self.level = level

    def organise_inputs(self, *args: Any) -> DeviceParam:
        return DeviceParam(*args)

    def _run_task(self, inputs: DeviceParam) -> TaskOutput:
        # We create a new Status rather than calling back to the TaskStatus,
        # to encourage composability in this way. This may not be the only
        # requirement etc.
        monitor_status = Status()

        def monitor_device():
            value = inputs.device.get()
            while value < self.level:
                time.sleep(0.1)  # Polling rate
                value = inputs.device.get()
            self.add_result(value)
            self.add_result(time.time())
            monitor_status.set_finished()

        Thread(target=monitor_device).start()
        yield from self._add_callback_or_complete(monitor_status)


class GridScanTask(BlueskyTask["GridScanTask.GridScanParams"]):
    """
    Runs a scan that is fast compared to the movement of the slow outer axis,
    for test purposes it takes ~0 time, meaning we should not miss any triggers.
    """

    @dataclass
    class GridScanParams(Input):
        detectors: List[Device]
        motorx: Device
        motory: Device
        startx: float = 0
        starty: float = 0
        stopx: float = 5
        stopy: float = 5
        numx: int = 5
        numy: int = 5

    def organise_inputs(self, *args: Any) -> GridScanParams:
        return GridScanTask.GridScanParams(*args)

    def _run_task(self, inputs: GridScanParams) -> TaskOutput:
        self.add_result(time.time())
        # Returns a UUID
        yield from grid_scan(
            inputs.detectors,
            inputs.motorx,
            inputs.startx,
            inputs.stopx,
            inputs.numx,
            inputs.motory,
            inputs.starty,
            inputs.stopy,
            inputs.numy,
        )
        # Scan is synchronous so we are complete now
        yield from self._add_callback_or_complete(None)


def test_order_of_tasks_ignored():
    ramping_motor = RampingMotor()
    ramping_task = InitiateRampingTask("")
    task_graph = TaskGraph({ramping_task: set()}, {ramping_task: ["TR6"]}, {})
    triggers = []
    scans = []
    for i in range(5):
        # Our triggers are backwards compared to the order they will activate
        trigger_task = TriggerTask(4 - i)
        scan_task = GridScanTask(f"Running scan at {i}")
        triggers.append(trigger_task)
        scans.append(scan_task)
        task_graph += TaskGraph(
            {trigger_task: {}, scan_task: {trigger_task}},
            {
                scan_task: ["detectors", "motorx", "motory"],
                trigger_task: ["TR6"]  # TR6 not in scan, so would not be read into
                # documents as is! We would actually want to either subscribe to it,
                # or read it in the grid scans, but for the purposes of proving it is
                # detached from logic of grid scan, we keep seperate
            },
            {},
        )

    RE = RunEngine({})
    RE(
        decision_engine_plan(
            task_graph,
            {
                "TR6": ramping_motor,
                "detectors": [det1],
                "motorx": motor1,
                "motory": motor2,
            },
        )
    )

    for i in range(5):
        # We read our triggers and scans back in reverse order, meaning the logic is
        # the same
        trigger_task = triggers[4 - i]
        trigger_results = trigger_task.get_results(["Location", "Time"])
        scan_task = scans[4 - i]
        scan_results = scan_task.get_results(["Time"])
        assert trigger_results["Time"] < scan_results["Time"]
        # Did not miss a read
        assert abs(trigger_results["Location"] - trigger_task.level) < 0.2
        if i > 0:
            previous_results = triggers[5 - i].get_results(["Location", "Time"])
            assert previous_results["Time"] < trigger_results["Time"]
            assert previous_results["Location"] < trigger_results["Location"]


def test_run():
    ramping_motor = RampingMotor()
    # TODO: This should probably wait until all Trigger tasks have been started?
    ramping_task = InitiateRampingTask("Initiate Ramping")
    task_graph = TaskGraph({ramping_task: set()}, {ramping_task: ["TR6"]}, {})
    triggers = []
    scans = []
    for i in range(5):
        trigger_task = TriggerTask(i)
        scan_task = GridScanTask(f"Running scan at {i}")
        triggers.append(trigger_task)
        scans.append(scan_task)
        task_graph += TaskGraph(
            {trigger_task: {}, scan_task: {trigger_task}},
            {scan_task: ["detectors", "motorx", "motory"], trigger_task: ["TR6"]},
            {},
        )

    RE = RunEngine({})
    RE(
        decision_engine_plan(
            task_graph,
            {
                "TR6": ramping_motor,
                "detectors": [det1],
                "motorx": motor1,
                "motory": motor2,
            },
        )
    )

    for i in range(5):
        trigger_task = triggers[i]
        trigger_results = trigger_task.get_results(["Location", "Time"])
        scan_task = scans[i]
        scan_results = scan_task.get_results(["Time"])
        assert trigger_results["Time"] < scan_results["Time"]
        # Did not miss a read
        assert abs(trigger_results["Location"] - trigger_task.level) < 0.2
        if i > 0:
            previous_results = triggers[i - 1].get_results(["Location", "Time"])
            assert previous_results["Time"] < trigger_results["Time"]
            assert previous_results["Location"] < trigger_results["Location"]
