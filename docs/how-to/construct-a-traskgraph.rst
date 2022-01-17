How to construct a TaskGraph
========================

A TaskGraph contains a trio of mappings: from each task to every task it directly depends upon, or cannot be run
concurrently with, from each task to the names of all the inputs it requires for execution and from each task to the
names of all of the outputs it will provide.
This allows for the output of a task to override initial values, or the output values of previous tasks: devices, seek
values, read back values should therefore either be named sensibly to prevent, or the TaskGraph should be constructed
with this behaviour in mind.

.. code:: python

    # A task graph with one task that must be run before another
    def simple_task_graph():
        first_task = BlueskyTask("Task must run first")
        second_task = BlueskyTask("Task runs second")
        return TaskGraph({first_task: [], second_task: [first_task]}, {}, {})

    # A task graph where the input of the second task is the output of the first
    def task_graph_with_outputs():
        first_task = BlueskyTask("Outputs necessary future input")
        second_task = BlueskyTask("Input from previous")
        return TaskGraph({first_task: [], second_task: [first_task]},
            {second_task: ["information"]}, {first_task: ["information"]})

    # Task graphs may be constructed by addition of task graphs, which creates a graph with all tasks from both with
    #  no interdependencies.
    graph = simple_task_graph() + task_graph_with_outputs()


    # A task graph can be dependent on a previously constructed task graph, or can be depended on by a previously
    #  constructed task graph.
    #  A task graph that is dependent on another places all tasks in the other as a dependency for every task in it.

    # All tasks in task_graph_with_outputs would run first, then all in simple_task_graph
    graph = simple_task_graph().depends_on(task_graph_with_outputs())
    # All tasks in simple_task_graph would run first, then all in task_graph_with_outputs
    graph = simple_task_graph().is_depended_on_by(task_graph_with_outputs())

    # These operations can be chained


