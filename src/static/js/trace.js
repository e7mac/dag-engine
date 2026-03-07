const Trace = {
  clear() {
    document.getElementById('trace-list').innerHTML =
      '<div class="empty-state" style="font-size:12px;padding:20px">Run a workflow to see the execution trace</div>';
  },

  render(trace, fullRun = null) {
    const el = document.getElementById('trace-list');
    if (!trace.nodes || trace.nodes.length === 0) {
      el.innerHTML = '<div class="empty-state" style="font-size:12px;padding:20px">No trace data</div>';
      return;
    }
    const nodeRuns = fullRun ? fullRun.node_runs || {} : {};
    const resumeBtn = fullRun && fullRun.status === 'failed'
      ? `<div style="padding:8px 12px;border-bottom:1px solid var(--border)"><button class="primary sm" onclick="Runner.resume('${fullRun.run_id}')">Resume from failure</button></div>`
      : '';
    el.innerHTML = resumeBtn + trace.nodes.map((n, i) => {
      const last = i === trace.nodes.length - 1;
      const dur = n.duration_ms != null ? n.duration_ms.toFixed(0) + 'ms' : '';
      const branch = n.branch_taken ? `<span class="branch-badge">${UI.esc(n.branch_taken)}</span>` : '';
      const attempts = n.attempts > 1 ? ` | ${n.attempts} attempts` : '';
      const startTime = n.started_at ? n.started_at.replace(/^.*T/, '').replace(/\+.*$/, '') : '';
      const nr = nodeRuns[n.node_id];
      let details = '';
      if (nr) {
        const sections = [];
        if (n.started_at || n.completed_at) sections.push({ label: 'Timing', data: { started_at: n.started_at, completed_at: n.completed_at, duration_ms: n.duration_ms } });
        if (nr.input) sections.push({ label: 'Input', data: nr.input });
        if (nr.output) sections.push({ label: 'Output', data: nr.output });
        if (nr.error) sections.push({ label: 'Error', data: nr.error });
        if (sections.length > 0) {
          const uid = 'detail-' + n.node_id.replace(/[^a-zA-Z0-9]/g, '_') + '-' + i;
          details = `<div class="trace-toggle" onclick="UI.toggleDetail('${uid}')">Show details</div>
            <div class="trace-detail" id="${uid}" style="display:none">${sections.map(s =>
              `<div class="detail-section"><span class="detail-label">${s.label}</span><pre class="detail-json">${UI.esc(typeof s.data === 'string' ? s.data : JSON.stringify(s.data, null, 2))}</pre></div>`
            ).join('')}</div>`;
        }
      }
      return `<div class="trace-node" data-node-id="${UI.esc(n.node_id)}">
        <div class="trace-line">
          <div class="trace-dot ${n.status}"></div>
          ${last ? '' : '<div class="trace-connector"></div>'}
        </div>
        <div class="trace-info">
          <div class="node-label">${UI.esc(n.node_id)}${branch}</div>
          <div class="node-meta">${n.status}${dur ? ' | ' + dur : ''}${attempts}${startTime ? ' | ' + startTime : ''}</div>
          ${details}
        </div>
      </div>`;
    }).join('');

    // Attach hover handlers
    el.querySelectorAll('.trace-node[data-node-id]').forEach(row => {
      row.addEventListener('mouseenter', () => {
        State.highlightedNodeId = row.dataset.nodeId;
        row.classList.add('highlight');
        if (State.lastDAGArgs.wf) DAG.draw(State.lastDAGArgs.wf, State.lastDAGArgs.trace);
      });
      row.addEventListener('mouseleave', () => {
        State.highlightedNodeId = null;
        row.classList.remove('highlight');
        if (State.lastDAGArgs.wf) DAG.draw(State.lastDAGArgs.wf, State.lastDAGArgs.trace);
      });
    });
  },

  renderStats(data) {
    const bar = document.getElementById('stats-bar');

    // Success rate color
    const rate = data.runs.success_rate;
    let rateClass = 'green';
    if (rate < 70) rateClass = 'red';
    else if (rate < 90) rateClass = 'yellow';

    let html = `
      <div class="stat-card">
        <div class="stat-label">Runs</div>
        <div class="stat-value">${data.totals.runs}</div>
        <div class="stat-sub">${data.runs.completed} passed / ${data.runs.failed} failed</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Success Rate</div>
        <div class="stat-value ${rateClass}">${rate.toFixed(1)}%</div>
        <div class="stat-sub">${data.runs.completed + data.runs.failed} finished</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Avg Latency</div>
        <div class="stat-value">${data.latency.avg_ms.toFixed(0)}<span style="font-size:12px;font-weight:400">ms</span></div>
        <div class="stat-sub">p95 ${data.latency.p95_ms.toFixed(0)}ms / max ${data.latency.max_ms.toFixed(0)}ms</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Retries</div>
        <div class="stat-value">${data.totals.retries}</div>
        <div class="stat-sub">${data.totals.nodes_succeeded} nodes ok / ${data.totals.nodes_failed} failed</div>
      </div>`;

    // Per-workflow table
    const wfKeys = Object.keys(data.per_workflow);
    if (wfKeys.length > 0) {
      html += `<div class="stat-card" style="min-width:200px">
        <div class="stat-label">Per Workflow</div>
        <table class="per-wf-table">
          <tr><th>Workflow</th><th>Runs</th><th>Pass</th><th>Avg ms</th></tr>`;
      wfKeys.forEach(wfId => {
        const w = data.per_workflow[wfId];
        html += `<tr>
          <td>${UI.esc(wfId)}</td>
          <td>${w.runs}</td>
          <td>${w.completed}/${w.runs}</td>
          <td>${w.avg_latency_ms.toFixed(0)}</td>
        </tr>`;
      });
      html += `</table></div>`;
    }

    bar.innerHTML = html;
  },
};
