Constructing a ControlObject
============================

A ControlObject [name TBD] is an object that encompasses whatever is required to allow automatic scheduling of
TaskGraphs and handling of exceptions. It holds the RunEngine that will process the plans and installs itself as a
Suspender: this suspender can be configured to allow for a number of non-fatal exceptions, instead suspending when tasks
with the same name reaches a threshold of consecutive failures. The Control Object holds a subset of beamline objects
and configuration necessary to run task graphs: all these objects are passed to the task graphs.
A ControlObject could contain additional Suspenders, for example to limit the number of runs before handing control back,
and should disable these suspenders when it does so.

.. code:: python

    # Command to be called to hand over control of the RunEngine to the ControlObject. This should not be called from
    #  within a loop: the RunEngine will throw an exception if the upstream stack is too high. It may contain the logic
    #  for handing back control after a number of runs or other control logic.
    def run_task_graphs(self):
        self._run_engine(multiple_task_graphs())

    # Command to allow an external RunEngine to be passed multiple task graphs, without
    #  installing suspenders etc.
    # May also contain control logic
    def multiple_task_graphs(self) -> Generator[Msg, None, None]:
        while not self._should_stop_at_end_of_next_run:
            yield from self.decision_engine_plan(
                self._create_next_graph(self.known_values)
            )

    # Creates the next task graph from the known values of the ControlObject: for example, the graph might differ on the
    #  first run after an interlock has been triggered, or this method could include a call to an external service that
    #  gives a recipe to construct the next graph. The graph could optimise depending on device location etc.
    # Control logic should not be present, except by the throwing of known exceptions
    #  for Suspenders installed on the RunEngine to catch
    def _create_next_graph(self, overrides: Dict[str, Any] = None) -> TaskGraph:
        ...

