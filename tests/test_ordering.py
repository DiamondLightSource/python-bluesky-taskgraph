from unittest.mock import MagicMock, Mock, call

from bluesky import RunEngine
from ophyd.sim import SynAxis

from python_bluesky_taskgraph.core.decision_engine import decision_engine_plan
from python_bluesky_taskgraph.core.task_graph import TaskGraph
from python_bluesky_taskgraph.tasks.behavioural_tasks import NoOpTask
from python_bluesky_taskgraph.tasks.stub_tasks import SetTask

"""
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

"""


def test_order_of_tasks():
    manager = MagicMock()
    first_task = NoOpTask("First Task")
    first_task.execute = MagicMock(wraps=first_task.execute)
    first_task.get_results = MagicMock(wraps=first_task.get_results)
    second_task = NoOpTask("Second Task")
    second_task.execute = MagicMock(wraps=second_task.execute)
    second_task.get_results = MagicMock(wraps=second_task.get_results)
    third_task = NoOpTask("Third Task")
    third_task.execute = MagicMock(wraps=third_task.execute)
    third_task.get_results = MagicMock(wraps=third_task.get_results)

    manager.configure_mock(
        fte=first_task.execute,
        ftr=first_task.get_results,
        tte=third_task.execute,
        ttr=third_task.get_results,
        ste=second_task.execute,
        str=second_task.get_results,
    )

    tasks = TaskGraph(
        {first_task: {}, second_task: {first_task}, third_task: {second_task}}, {}, {}
    )

    expected_calls = [
        call.fte([]),
        call.ftr([]),
        call.ste([]),
        call.str([]),
        call.tte([]),
        call.ttr([]),
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls


def test_graph_dependencies_depends():
    manager = MagicMock()
    first_task = NoOpTask("First Task")
    first_task.execute = MagicMock(wraps=first_task.execute)
    first_task.get_results = MagicMock(wraps=first_task.get_results)
    second_task = NoOpTask("Second Task")
    second_task.execute = MagicMock(wraps=second_task.execute)
    second_task.get_results = MagicMock(wraps=second_task.get_results)
    third_task = NoOpTask("Third Task")
    third_task.execute = MagicMock(wraps=third_task.execute)
    third_task.get_results = MagicMock(wraps=third_task.get_results)

    manager.configure_mock(
        fte=first_task.execute,
        ftr=first_task.get_results,
        tte=third_task.execute,
        ttr=third_task.get_results,
        ste=second_task.execute,
        str=second_task.get_results,
    )

    tasks = TaskGraph({second_task: {}, third_task: {second_task}}, {}, {})
    tasks = tasks.depends_on(TaskGraph({first_task: set()}, {}, {}))

    for task in second_task, third_task:
        assert first_task in tasks.graph[task]

    expected_calls = [
        call.fte([]),
        call.ftr([]),
        call.ste([]),
        call.str([]),
        call.tte([]),
        call.ttr([]),
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls


def test_graph_dependencies_dependant():
    manager = MagicMock()
    first_task = NoOpTask("First Task")
    first_task.execute = MagicMock(wraps=first_task.execute)
    first_task.get_results = MagicMock(wraps=first_task.get_results)
    second_task = NoOpTask("Second Task")
    second_task.execute = MagicMock(wraps=second_task.execute)
    second_task.get_results = MagicMock(wraps=second_task.get_results)
    third_task = NoOpTask("Third Task")
    third_task.execute = MagicMock(wraps=third_task.execute)
    third_task.get_results = MagicMock(wraps=third_task.get_results)

    manager.configure_mock(
        fte=first_task.execute,
        ftr=first_task.get_results,
        tte=third_task.execute,
        ttr=third_task.get_results,
        ste=second_task.execute,
        str=second_task.get_results,
    )

    tasks = TaskGraph({first_task: {}, second_task: {first_task}}, {}, {})
    tasks = tasks.is_depended_on_by(TaskGraph({third_task: set()}, {}, {}))

    for task in second_task, third_task:
        assert first_task in tasks.graph[task]

    expected_calls = [
        call.fte([]),
        call.ftr([]),
        call.ste([]),
        call.str([]),
        call.tte([]),
        call.ttr([]),
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks))

    # TODO: mock.assert_has_calls doesn't play with other calls between?
    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls


def test_graph_runs_tasks_concurrent():
    slow_task = SetTask("Set slow moving device")
    slow_task.get_results = MagicMock(wraps=slow_task.get_results)
    fast_task = SetTask("Set fast moving device")
    fast_task.get_results = MagicMock(wraps=fast_task.get_results)

    after_slow = NoOpTask(name="After slow movement")
    after_slow.execute = MagicMock(wraps=after_slow.execute)
    after_slow.get_results = MagicMock(wraps=after_slow.get_results)
    after_fast = NoOpTask(name="After fast movement")
    after_fast.execute = MagicMock(wraps=after_fast.execute)
    after_fast.get_results = MagicMock(wraps=after_fast.get_results)

    slow_device = SynAxis(name="Slow Device", delay=3)
    fast_device = SynAxis(name="Fast Device", delay=0.5)
    location = 7

    tasks = TaskGraph(
        {
            slow_task: {},
            fast_task: {},
            after_slow: {slow_task},
            after_fast: {fast_task},
        },
        {
            slow_task: ["slow device", "location"],
            fast_task: ["fast device", "location"],
        },
        {},
    )

    manager = Mock()
    # Cannot guarantee order of starting fast, slow task
    manager.configure_mock(
        ftr=fast_task.get_results,
        afte=after_fast.execute,
        aftr=after_fast.get_results,
        ttr=slow_task.get_results,
        ste=after_slow.execute,
        str=after_slow.get_results,
    )

    expected_calls = [
        call.ftr([]),
        call.afte([]),
        call.aftr([]),
        call.ttr([]),
        call.ste([]),
        call.str([]),
    ]
    re = RunEngine({})

    re(
        decision_engine_plan(
            tasks,
            {
                "slow device": slow_device,
                "fast device": fast_device,
                "location": location,
            },
        )
    )

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls
