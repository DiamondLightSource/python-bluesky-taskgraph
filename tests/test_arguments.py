from typing import List
from unittest.mock import MagicMock, call

from bluesky import RunEngine
from mocks import DefaultArgumentMock, ExampleTask, MultipleArgumentTask

from python_bluesky_taskgraph.core.decision_engine import decision_engine_plan
from python_bluesky_taskgraph.core.task_graph import TaskGraph
from python_bluesky_taskgraph.tasks.behavioural_tasks import NoOpTask


def get_results(entries: List[str]):
    return zip(entries, {"passed"})


def test_taskgraph_passes_args():
    manager = MagicMock()
    first_task = NoOpTask("First Task")
    first_task.execute = MagicMock(wraps=first_task.execute)
    # Inject a return from the NoOpTask
    first_task.get_results = MagicMock(wraps=get_results)
    second_task = NoOpTask("First Task")
    second_task.execute = MagicMock(wraps=second_task.execute)
    second_task.get_results = MagicMock(wraps=second_task.get_results)

    manager.configure_mock(
        first=first_task.execute,
        second=first_task.get_results,
        third=second_task.execute,
        fourth=second_task.get_results,
    )

    tasks = TaskGraph(
        {first_task: {}, second_task: {first_task}},
        {first_task: ["input"], second_task: ["output arg"]},
        {first_task: ["output arg"]},
    )

    expected_calls = [
        call.first(["expected input"]),
        call.second(["output arg"]),
        call.third(["passed"]),
        call.fourth([]),
    ]

    re = RunEngine({})
    re(decision_engine_plan(tasks, {"input": "expected input"}))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls


def test_taskgraph_updates_args():
    manager = MagicMock()
    first_task = NoOpTask("First Task")
    first_task.execute = MagicMock(wraps=first_task.execute)
    # Inject a return from the NoOpTask
    first_task.get_results = MagicMock(wraps=get_results)
    second_task = NoOpTask("First Task")
    second_task.execute = MagicMock(wraps=second_task.execute)
    second_task.get_results = MagicMock(wraps=second_task.get_results)

    manager.configure_mock(
        first=first_task.execute,
        second=first_task.get_results,
        third=second_task.execute,
        fourth=second_task.get_results,
    )

    tasks = TaskGraph(
        {first_task: {}, second_task: {first_task}},
        {first_task: ["input"], second_task: ["output arg"]},
        {first_task: ["output arg"]},
    )

    expected_calls = [
        call.first(["expected input"]),
        call.second(["output arg"]),
        call.third(["passed"]),
        call.fourth([]),
    ]

    re = RunEngine({})
    re(
        decision_engine_plan(
            tasks, {"input": "expected input", "output arg": "replaced"}
        )
    )

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls


def test_task_constructs_tuple():
    manager = MagicMock()
    first_task = ExampleTask()
    first_task.execute = MagicMock(wraps=first_task.execute)
    first_task._run_task = MagicMock(wraps=first_task._run_task)

    manager.configure_mock(first=first_task.execute, second=first_task._run_task)

    tasks = TaskGraph(
        {first_task: set()}, {first_task: ["input"]}, {first_task: list()}
    )

    expected_calls = [
        call.first(["expected input"]),
        call.second(ExampleTask.SimpleInput("expected input")),
    ]

    re = RunEngine({})
    re(decision_engine_plan(tasks, {"input": "expected input"}))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls


def test_task_constructs_more_complicated_tuple():
    manager = MagicMock()
    first_task = MultipleArgumentTask()
    first_task.execute = MagicMock(wraps=first_task.execute)
    first_task._run_task = MagicMock(wraps=first_task._run_task)

    manager.configure_mock(first=first_task.execute, second=first_task._run_task)

    tasks = TaskGraph(
        {first_task: set()}, {first_task: ["input", "second"]}, {first_task: list()}
    )

    expected_calls = [
        call.first(["expected input", 7]),
        call.second(MultipleArgumentTask.SimpleInput("expected input", 7)),
    ]

    re = RunEngine({})
    re(decision_engine_plan(tasks, {"input": "expected input", "second": 7}))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls


def test_task_constructs_tuple_with_default_args():
    manager = MagicMock()
    first_task = DefaultArgumentMock()
    first_task.execute = MagicMock(wraps=first_task.execute)
    first_task._run_task = MagicMock(wraps=first_task._run_task)

    manager.configure_mock(first=first_task.execute, second=first_task._run_task)

    tasks = TaskGraph(
        {first_task: set()}, {first_task: ["input"]}, {first_task: list()}
    )

    expected_calls = [
        call.first(["expected input"]),
        call.second(DefaultArgumentMock.SimpleInput("expected input", 7)),
    ]

    re = RunEngine({})
    re(decision_engine_plan(tasks, {"input": "expected input"}))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls


def test_task_constructs_tuple_with_overwritten_default_args():
    manager = MagicMock()
    first_task = DefaultArgumentMock()
    first_task.execute = MagicMock(wraps=first_task.execute)
    first_task._run_task = MagicMock(wraps=first_task._run_task)

    manager.configure_mock(first=first_task.execute, second=first_task._run_task)

    tasks = TaskGraph(
        {first_task: set()}, {first_task: ["input", "second"]}, {first_task: list()}
    )

    expected_calls = [
        call.first(["expected input", 8]),
        call.second(DefaultArgumentMock.SimpleInput("expected input", 8)),
    ]

    re = RunEngine({})
    re(decision_engine_plan(tasks, {"input": "expected input", "second": 8}))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert method_calls == expected_calls
