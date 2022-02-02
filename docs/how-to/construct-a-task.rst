How to construct a Task
=======================

A Task should extend BlueskyTask and overwrite BlueskyTask._run_task, unless finer control over the Status of the task
is required, in which case BlueskyTask.execute may be overwritten instead. The Status of the task- constructed by
execute()- should only be marked complete or failed when the task has complete: the plan stub task_callback is provided
and passes BlueskyTask.propagate_status as a callback to a Status constructed from the Statuses of any long running
operation monitored by the RunEngine, with the appropriate group.
The Task may instead set up an async call to monitor a subscription, construct a Status to complete when one of many
parallel tasks complete etc.: in each case, the _run_task method's final operation should yield a Msg.

.. code:: python

    # A Bad plan: the status of the task is assumed to be done almost as soon as the move is begun, and the the second
    #  read is unlikely to be at the end of the movement:
    def _run_task(self, slow_moving_device: Device, distant_location: float) -> PlanOutput:
        self.add_result(read_device(slow_moving_device))  # Read initial location
        yield from abs_set(slow_moving_device, distant_location)
        self.add_result(read_device(slow_moving_device))  # Read final location
        self._status.set_finished()
        yield Msg('null')

    ''''''

    # The same plan but with consideration taken for long running movements
    def _run_task(self, slow_moving_device: Device, distant_location: float) -> PlanOutput:
        self.add_result(read_device(slow_moving_device))  # Read initial location
        yield from abs_set(slow_moving_device, distant_location, group="slow movement")
        yield from task_callback(self, group="slow movement")

    def propagate_status(self, status: DeviceStatus) -> None:
        # Status is complete so shouldn't need a timeout?
        exception = status.exception(None)
        if exception:
            self._status.set_exception(exception)
        else:
            self.add_result(read_device(status.device))  # Read final location
            self._status.set_finished()  # Mark status complete when move is complete and all results available


How big should a task be?
========================

A Task should be a behavioural chunk of operations: it may make sense to have a task that is a single operation e.g.
moving a single device, if the Task is appropriately named to show what behaviour it enables: e.g. "Move Devices Out of
Beam", where devices is a single device, but knowing that devices are out of the beam enabled a future behaviour.
Tasks need not be constrained by what can be run concurrently: RunEngine waits should be used to orchestrate parallelism
within tasks.

    Moving motorA and motorB consecutively as concurrent motion dangerous, to enable behaviour of "resetting all motors"
    -> Same task, with Bluesky wait plans to ensure motors not moving concurrently

    Moving motorA while concurrently setting up file systems -> Non-dependent tasks

    Moving motorA to reset position explicitly prior to moving detector into position -> Dependent tasks


Optional and Conditional Tasks
========================

Tasks that are optional based on initial conditions (such as tasks that are run during the first run after an interlock
is enabled) may be conditionally added to the TaskGraph by its constructing ControlObject, or else may be wrapped in an
ConditionalTask. ConditionalTask takes an optional second task, for constructing a choice of one task or another:
ConditionalTasks, regardless of which behaviour is being enabled, should be approached with considerable caution with
regards to what is available as output after they have been run: as outputs are gathered by zipping with the names, and
this truncates to the shorter of the lists, optional tasks are not required to return anything, in which case the
arguments they output should already be available from prior tasks (with dependencies ensuring they are prior) or else
in initial conditions.


Task argument ordering
========================

Task input arguments should prioritise
    primarily: Devices
    secondarily: beamline configuration
    then: all other arguments
