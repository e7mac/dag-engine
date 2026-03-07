const Runner = {
  async execute() {
    if (!State.selectedWorkflowId) return;

    const errEl = document.getElementById('run-error');

    let ctx;
    try {
      ctx = JSON.parse(document.getElementById('run-context').value);
    } catch (e) {
      errEl.textContent = 'Invalid JSON: ' + e.message;
      errEl.style.display = 'block';
      return;
    }

    const sandbox = document.getElementById('run-sandbox').checked;

    try {
      const { run_id } = await API.fetch(
        `/workflows/${State.selectedWorkflowId}/run`,
        {
          method: 'POST',
          body: JSON.stringify({ initial_context: ctx, sandbox_mode: sandbox }),
        }
      );

      UI.closeModal('run-modal');
      UI.toast('Run started: ' + run_id.slice(0, 8) + '...', 'success');
      Runner.poll(run_id);
    } catch (e) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
    }
  },

  poll(runId) {
    if (State.pollTimer) {
      clearInterval(State.pollTimer);
    }

    let attempts = 0;

    State.pollTimer = setInterval(async () => {
      attempts++;

      try {
        const run = await API.fetch(`/runs/${runId}`);

        // Update runs list
        const idx = State.runs.findIndex(r => r.run_id === runId);
        if (idx >= 0) {
          State.runs[idx] = run;
        } else {
          State.runs.push(run);
        }
        Sidebar.renderRunList();

        // Stop polling when run finishes
        if (run.status === 'completed' || run.status === 'failed') {
          clearInterval(State.pollTimer);
          State.pollTimer = null;

          Sidebar.selectRun(runId);
          UI.toast(
            `Run ${run.status}`,
            run.status === 'completed' ? 'success' : 'error'
          );

          if (State.statsVisible) {
            API.fetchStats();
          }
        }
      } catch (e) {
        if (attempts > 30) {
          clearInterval(State.pollTimer);
          State.pollTimer = null;
        }
      }
    }, 500);
  },

  async resume(runId) {
    try {
      await API.fetch(`/runs/${runId}/resume`, { method: 'POST' });
      UI.toast('Resuming run ' + runId.slice(0, 8) + '...', 'success');
      Runner.poll(runId);
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },
};
