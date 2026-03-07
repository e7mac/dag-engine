const API = {
  async fetch(path, opts = {}) {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
    }
    return res.json();
  },

  async fetchWorkflows() {
    try {
      const list = await API.fetch('/workflows');
      State.workflows = {};
      list.forEach(w => State.workflows[w.id] = w);
      Sidebar.renderWorkflowList();
    } catch (e) { /* server may not be running */ }
  },

  async fetchRuns() {
    try {
      State.runs = await API.fetch('/runs');
      Sidebar.renderRunList();
    } catch (e) { /* ignore */ }
  },

  async fetchStats() {
    try {
      const data = await API.fetch('/stats');
      Trace.renderStats(data);
    } catch (e) { /* server may not be running */ }
  },
};
