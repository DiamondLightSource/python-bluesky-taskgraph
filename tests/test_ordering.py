from time import sleep
from typing import Any, Optional
from unittest.mock import Mock, call

from bluesky import RunEngine
from bluesky.plan_stubs import abs_set
from bluesky.protocols import Status
from ophyd import Device
from ophyd.sim import SynAxis

from src.bluesky_taskgraph_runner.core.decision_engine import decision_engine_plan
from src.bluesky_taskgraph_runner.core.task_graph import TaskGraph
from src.bluesky_taskgraph_runner.core.types import PlanOutput
from src.bluesky_taskgraph_runner.tasks.stub_tasks import SetTask
from mocks import mock_task

'''
Suggested method of composing tasks:
final_tasks = get_final_tasks()
penultimate_tasks = get_penultimate_tasks()
...
second_tasks = get_second_tasks()
first_tasks = get_first_tasks()

tasks = final_tasks.depends_on(penultimate_tasks).[...]
    .depends_on(second_tasks).depends_on(first_tasks)
or 
tasks = first_tasks.are_dependent_on(second_tasks)...

'''


def test_order_of_tasks():
    first_task = mock_task(name="First Task")
    second_task = mock_task(name="Second Task")
    third_task = mock_task(name="Third Task")

    tasks = TaskGraph({first_task: [],
                       second_task: [first_task],
                       third_task: [second_task]}, {}, {})
    manager = Mock()

    manager.first_task = first_task
    manager.second_task = second_task
    manager.third_task = third_task

    expected_calls = [
        call.first_task.execute([]),
        call.first_task.get_results([]),
        call.second_task.execute([]),
        call.second_task.get_results([]),
        call.third_task.execute([]),
        call.third_task.get_results([])
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks))

    while re.state != 'idle':
        print("sleep")
        sleep(0.1)

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert (method_calls == expected_calls)


def test_graph_dependencies_depends():
    first_task = mock_task(name="First Task")
    second_task = mock_task(name="Second Task")
    third_task = mock_task(name="Third Task")

    tasks = TaskGraph({second_task: [], third_task: [second_task]}, {}, {})
    tasks = tasks.depends_on(TaskGraph({first_task: []}, {}, {}))

    for task in second_task, third_task:
        assert first_task in tasks.graph[task]
    manager = Mock()

    manager.first_task = first_task
    manager.second_task = second_task
    manager.third_task = third_task

    expected_calls = [
        call.first_task.execute([]),
        call.first_task.get_results([]),
        call.second_task.execute([]),
        call.second_task.get_results([]),
        call.third_task.execute([]),
        call.third_task.get_results([])
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert (method_calls == expected_calls)


def test_graph_dependencies_dependant():
    first_task = mock_task(name="First Task")
    second_task = mock_task(name="Second Task")
    third_task = mock_task(name="Third Task")

    tasks = TaskGraph({first_task: [], second_task: [first_task]}, {}, {})
    tasks = tasks.is_depended_on_by(TaskGraph({third_task: []}, {}, {}))

    for task in second_task, third_task:
        assert first_task in tasks.graph[task]
    manager = Mock()

    manager.first_task = first_task
    manager.second_task = second_task
    manager.third_task = third_task

    expected_calls = [
        call.first_task.execute([]),
        call.first_task.get_results([]),
        call.second_task.execute([]),
        call.second_task.get_results([]),
        call.third_task.execute([]),
        call.third_task.get_results([])
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks))

    # TODO: mock.assert_has_calls doesn't play with other calls between?
    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert (method_calls == expected_calls)


def test_graph_runs_tasks_concurrent():
    slow_task = mock_task(SetTask("Set slow moving device"))
    fast_task = mock_task(SetTask("Set fast moving device"))
    after_slow = mock_task(name="After slow movement")
    after_fast = mock_task(name="After fast movement")

    slow_device = SynAxis(name="Slow Device", delay=3)
    fast_device = SynAxis(name="Fast Device", delay=0.5)
    location = 7

    def slow_move(device: Device, value: Any,
                  group: Optional[str] = None) -> PlanOutput:
        ret: Optional[Status] = yield from abs_set(device, value,
                                                   group=group or slow_task.name())
        # The wait is a success if the set was a success
        ret.add_callback(slow_task.propagate_status)
        return slow_task._status

    def fast_move(device: Device, value: Any,
                  group: Optional[str] = None) -> PlanOutput:
        ret: Optional[Status] = yield from abs_set(device, value,
                                                   group=group or fast_task.name())
        # The wait is a success if the set was a success
        ret.add_callback(fast_task.propagate_status)
        return fast_task._status

    # Run the actual set behaviour,
    #   which sets a status to done only once the move is complete
    slow_task._run_task.side_effect = slow_move
    fast_task._run_task.side_effect = fast_move

    tasks = TaskGraph({slow_task: [],
                       fast_task: [],
                       after_slow: [slow_task],
                       after_fast: [fast_task]},
                      {slow_task: ["slow device", "location"],
                       fast_task: ["fast device", "location"]},
                      {})

    manager = Mock()

    manager.slow_task = slow_task
    manager.fast_task = fast_task
    manager.after_slow = after_slow
    manager.after_fast = after_fast

    # Cannot guarantee order of slow task and fast task beginning, but only want to
    # guarantee that after-fast runs before slow finishes
    expected_calls = [
        call.slow_task.execute([slow_device, location]),
        call.after_fast.execute([]),
        call.after_fast.get_results([]),
        call.slow_task.get_results([]),
        call.after_slow.execute([]),
        call.after_slow.get_results([])
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks,
                            {"slow device": slow_device,
                             "fast device": fast_device,
                             "location": location}))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert (method_calls == expected_calls)
