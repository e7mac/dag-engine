// Redraw DAG on window resize
window.addEventListener('resize', () => {
  if (State.lastDAGArgs.wf) {
    DAG.draw(State.lastDAGArgs.wf, State.lastDAGArgs.trace);
  } else if (State.selectedWorkflowId && State.workflows[State.selectedWorkflowId]) {
    DAG.draw(State.workflows[State.selectedWorkflowId]);
  }
});

// Load initial data
API.fetchWorkflows();
API.fetchRuns();
