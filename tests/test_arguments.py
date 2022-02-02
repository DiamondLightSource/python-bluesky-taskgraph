from typing import List
from unittest.mock import Mock, call

from bluesky import RunEngine

from src.bluesky_taskgraph_runner.core.decision_engine import decision_engine_plan
from src.bluesky_taskgraph_runner.core.task_graph import TaskGraph
from mocks import mock_task


def test_taskgraph_passes_args():
    first_task = mock_task(name="First Task")
    second_task = mock_task(name="Second Task")

    def return_passed(keys: List[str]):
        return zip(keys, ["passed"])

    first_task.get_results.side_effect = return_passed

    tasks = TaskGraph({first_task: [], second_task: [first_task]},
                      {first_task: ["input"], second_task: ["output arg"]},
                      {first_task: ["output arg"]})

    manager = Mock()

    manager.first_task = first_task
    manager.second_task = second_task

    expected_calls = [
        call.first_task.execute(["expected input"]),
        call.first_task.get_results(["output arg"]),
        call.second_task.execute(["passed"]),
        call.second_task.get_results([])
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks,
                            {"output": "expected output",
                             "input": "expected input"}))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert (method_calls == expected_calls)


def test_taskgraph_updates_args():
    first_task = mock_task(name="First Task")
    second_task = mock_task(name="Second Task")

    def return_passed(keys: List[str]):
        return zip(keys, ["updated arg"])

    first_task.get_results.side_effect = return_passed

    tasks = TaskGraph({first_task: [], second_task: [first_task]},
                      {first_task: ["input"], second_task: ["input"]},
                      {first_task: ["input"]})

    manager = Mock()

    manager.first_task = first_task
    manager.second_task = second_task

    expected_calls = [
        call.first_task.execute(["initial arg"]),
        call.first_task.get_results(["input"]),
        call.second_task.execute(["updated arg"]),
        call.second_task.get_results([])
    ]
    re = RunEngine({})

    re(decision_engine_plan(tasks, {"input": "initial arg"}))

    for expected_call in expected_calls:
        assert expected_call in manager.mock_calls

    method_calls = [calls for calls in manager.method_calls if calls in expected_calls]
    assert (method_calls == expected_calls)
