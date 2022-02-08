How to construct a Task
=======================

A Task should extend BlueskyTask, with a Generic argument of a Dataclass extending
Input: this dataclass can be defined within the task itself, with forward referenced
typing. It must overwrite BlueskyTask._run_task, and provide a
mapping to its dataclass type in BlueskyTask.organise_args.
BlueskyTask.execute logs the start time of the task and wraps the internal call and
should not be overwritten.
The Status of the task- which is created on task creation- should only be marked
complete or failed when the task has complete: BlueskyTask.propagate_status can be passed as a
callback to a Status constructed from the Status[es] of any long running
operation monitored by the RunEngine.
The Task may instead set up an async call to monitor a subscription, construct a Status to complete when one of many
parallel tasks complete etc.

.. code:: python

    # A Bad plan: the status of the task is assumed to be done almost as soon as the move is begun, and the the second
    #  read is unlikely to be at the end of the movement:
    class SetArgs(Input):
        device: Device
        location: Any

    def organise_inputs(*args) -> SetArgs:
        return SetArgs(*args)

    def _run_task(self, args: SetArgs) -> PlanOutput:
        self.add_result(read_device(args.device))  # Read initial location
        yield from abs_set(args.device, args.location)
        self.add_result(read_device(args.device))  # Read final location
        self._status.set_finished()
        yield from self._add_callback_or_complete(None)

    ''''''

    # The same plan but with consideration taken for long running movements
    def _run_task(self, args: SetArgs) -> PlanOutput:
        self.add_result(read_device(args.device))  # Read initial location
        ret: Optional[Status] = yield from abs_set(args.device, args.location)
        yield from self._add_callback_or_complete(ret)

    def propagate_status(self, status: DeviceStatus) -> None:
        # Status is complete so shouldn't need a timeout?
        exception = status.exception(None)
        if exception:
            self._status.set_exception(exception)
        else:
            self.add_result(read_device(status.device))  # Read final location
            self._status.set_finished()  # Mark status complete when move is complete
                                         #  and all results available


How big should a task be?
=========================

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
==============================

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
