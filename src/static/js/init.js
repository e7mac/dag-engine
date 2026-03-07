window.addEventListener('resize', () => {
  if (State.lastDAGArgs.wf) {
    DAG.draw(State.lastDAGArgs.wf, State.lastDAGArgs.trace);
  } else if (State.selectedWorkflowId && State.workflows[State.selectedWorkflowId]) {
    DAG.draw(State.workflows[State.selectedWorkflowId]);
  }
});

API.fetchWorkflows();
API.fetchRuns();
