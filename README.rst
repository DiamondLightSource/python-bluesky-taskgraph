python_bluesky_taskgraph
===========================

|code_ci| |docs_ci| |coverage| |pypi_version| |license|

A library extending the Bluesky RunEngine to allow TaskGraphs to be run: TaskGraphs are intended to encourage
parallelism and composability compared to Bluesky native plans by breaking plans into conditional blocks, or tasks.

Work related to implementing a Task Graph runner (Decision Engine) in Bluesky, akin to the VMXi task graph runner in
Jython.

The decision engine plan is passed to the RunEngine, optionally by a ControlObject which constructs multiple TaskGraphs
according to either inbuilt logic or from a recipe involving an external source, and the RunEngine interrogates the plan
as a Msg generator.
A TaskGraph contains:

1. A dictionary of plan to a list of plans it is known to be dependent on or else unable to be run concurrently with
2. A dictionary of plan to list of strings, the names of the arguments it needs
   We force this to be defined for the task graph (rather than by each task) to prevent accessing prior args
   Multiple tasks may share an input argument name
   An input argument may be overwritten later by the output of a task, so a graph should be defined such that if args
   are going to be overwritten, the overwriting tasks should depend on any that require the previous value
3. A dictionary of plan to a list of strings, the names of the outputs it will provide
   We force this to be defined for the task graph (rather than by each task) to prevent overriding prior args
   The output strings should be at most the length of the outputs of the task, else will be truncated
   An output argument may overwrite a previous output or initial value, so care should be taken to either avoid this
   behaviour or have any overwriting tasks depend on any tasks requiring the previous value

The DecisionEnginePlan is additionally passed a dictionary of string to any necessary initial conditions or known values
atits creation. e.g.
- Beamline configurations, name etc.
- Any devices that will be required for the graph

Decision engine plans, their decision engines, the task graphs they are initialised with, and the tasks are intended to
be run once and then discarded.

Task graphs can be composed of smaller task graphs using the depends_on function, or by simple addition of plans.
Graph A + Graph B places every entry from each dictionary in Graph B into Graph A's, overwriting existing keys in A
Graph A being dependent on Graph B is equivalent to every task within Graph A being dependent on every task in Graph B,
then Graph A = Graph A + Graph B. After depends_on or graph addition, Graph B should be discarded to prevent accidental
running of tasks again, Graph A now contains all the information Task graphs should **not** contain the same task as
another graph other than these transient cases.


============== ==============================================================
PyPI           ``pip install python_bluesky_taskgraph``
Source code    https://github.com/DiamondLightSource/python-bluesky-taskgraph
Documentation  https://DiamondLightSource.github.io/python_bluesky_taskgraph
Releases       https://github.com/DiamondLightSource/python-bluesky-taskgraph/releases
============== ==============================================================

.. code:: python

    # The TaskGraph plan can utilise the native Bluesky RunEngine: in Python 3.8 or
    #  above
    RE = RunEngine({})
    # An example ControlObject, which could monitors the state of the beamline 'baton' and returns control when
    #  required, or else restarts collection when the baton is free.
    CO = UnattendedDataCollectionControlObject(RE)
    CO.run_task_graphs()

    # Or else, the RunEngine can run a decision_engine_plan, wrapping a TaskGraph
    RE(decision_engine_plan(task_graph, variables or {}))


.. |code_ci| image:: https://github.com/DiamondLightSource/python-bluesky-taskgraph/workflows/Code%20CI/badge.svg?branch=master
    :target: https://github.com/DiamondLightSource/python-bluesky-taskgraph/actions?query=workflow%3A%22Code+CI%22
    :alt: Code CI

.. |docs_ci| image:: https://github.com/DiamondLightSource/python-bluesky-taskgraph/workflows/Docs%20CI/badge.svg?branch=master
    :target: https://github.com/DiamondLightSource/python-bluesky-taskgraph/actions?query=workflow%3A%22Docs+CI%22
    :alt: Docs CI

.. |coverage| image:: https://codecov.io/gh/DiamondLightSource/python-bluesky-taskgraph/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/DiamondLightSource/python-bluesky-taskgraph
    :alt: Test Coverage

.. |pypi_version| image:: https://img.shields.io/pypi/v/python_bluesky_taskgraph.svg
    :target: https://pypi.org/project/python_bluesky_taskgraph
    :alt: Latest PyPI version

.. |license| image:: https://img.shields.io/badge/License-Apache%202.0-blue.svg
    :target: https://opensource.org/licenses/Apache-2.0
    :alt: Apache License

..
    Anything below this line is used when viewing README.rst and will be replaced
    when included in index.rst

See https://DiamondLightSource.github.io/python_bluesky_taskgraph for more detailed documentation.
