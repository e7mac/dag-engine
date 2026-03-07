const Sidebar = {
  renderWorkflowList() {
    const el = document.getElementById('workflow-list');
    const ids = Object.keys(State.workflows);
    if (ids.length === 0) {
      el.innerHTML = '<div style="font-size:12px;color:var(--text-dim);padding:4px">No workflows registered</div>';
      return;
    }
    el.innerHTML = ids.map(id => {
      const w = State.workflows[id];
      const nodeCount = Object.keys(w.nodes).length;
      const active = id === State.selectedWorkflowId ? ' active' : '';
      return `<div class="sidebar-item${active}" onclick="Sidebar.selectWorkflow('${id}')">
        <div class="dot" style="background:var(--accent)"></div>
        <span>${UI.esc(w.name)}</span>
        <span class="meta">${nodeCount}n</span>
      </div>`;
    }).join('');
  },

  renderRunList() {
    const el = document.getElementById('run-list');
    if (State.runs.length === 0) {
      el.innerHTML = '<div style="font-size:12px;color:var(--text-dim);padding:4px">No runs yet</div>';
      return;
    }
    el.innerHTML = State.runs.slice().reverse().map(r => {
      const active = r.run_id === State.selectedRunId ? ' active' : '';
      const short = r.run_id.slice(0, 8);
      return `<div class="sidebar-item${active}" onclick="Sidebar.selectRun('${r.run_id}')">
        <div class="dot run-status-${r.status}"></div>
        <span>${short}...</span>
        <span class="meta">${r.status}</span>
      </div>`;
    }).join('');
  },

  selectWorkflow(id) {
    State.selectedWorkflowId = id;
    State.selectedRunId = null;
    const wf = State.workflows[id];
    document.getElementById('toolbar').style.display = 'flex';
    document.getElementById('workflow-title').textContent = wf.name + ' v' + wf.version;
    document.getElementById('validation-box').innerHTML = '';
    document.getElementById('context-editor').style.display = 'block';
    document.getElementById('context-input').value = Workflow.buildDefaultContext(wf);
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('dag-canvas').style.display = 'block';
    Sidebar.renderWorkflowList();
    Sidebar.renderRunList();
    Trace.clear();
    DAG.draw(wf);
  },

  async selectRun(runId) {
    State.selectedRunId = runId;
    Sidebar.renderRunList();
    try {
      const [trace, fullRun] = await Promise.all([
        API.fetch(`/runs/${runId}/trace`),
        API.fetch(`/runs/${runId}`),
      ]);
      Trace.render(trace, fullRun);
      // Also select the workflow if it exists
      const run = State.runs.find(r => r.run_id === runId);
      if (run && State.workflows[run.workflow_id]) {
        State.selectedWorkflowId = run.workflow_id;
        const wf = State.workflows[run.workflow_id];
        document.getElementById('toolbar').style.display = 'flex';
        document.getElementById('workflow-title').textContent = wf.name + ' v' + wf.version;
        document.getElementById('empty-state').style.display = 'none';
        document.getElementById('dag-canvas').style.display = 'block';
        document.getElementById('context-editor').style.display = 'block';
        Sidebar.renderWorkflowList();
        DAG.draw(wf, trace);
      }
    } catch (e) {
      UI.toast('Could not load trace: ' + e.message, 'error');
    }
  },
};
