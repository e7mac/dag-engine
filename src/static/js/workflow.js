const Workflow = {
  extractContextVars(wf) {
    const vars = new Set();
    const re = /\{\{context\.([^}]+)\}\}/g;
    JSON.stringify(wf).replace(re, (_, v) => { vars.add(v.trim()); });
    return [...vars];
  },

  buildDefaultContext(wf) {
    const vars = Workflow.extractContextVars(wf);
    if (vars.length === 0) return '{}';
    const obj = {};
    vars.forEach(v => { obj[v] = 'example_' + v; });
    return JSON.stringify(obj, null, 2);
  },

  async register() {
    const textarea = document.getElementById('register-json');
    const errEl = document.getElementById('register-error');
    let json;
    try {
      json = JSON.parse(textarea.value);
    } catch (e) {
      errEl.textContent = 'Invalid JSON: ' + e.message;
      errEl.style.display = 'block';
      return;
    }
    try {
      const wf = await API.fetch('/workflows', { method: 'POST', body: JSON.stringify(json) });
      State.workflows[wf.id] = wf;
      UI.closeModal('register-modal');
      Sidebar.renderWorkflowList();
      Sidebar.selectWorkflow(wf.id);
      UI.toast('Workflow registered', 'success');
    } catch (e) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
    }
  },

  async loadExample(name) {
    const json = EXAMPLES[name];
    try {
      const wf = await API.fetch('/workflows', { method: 'POST', body: JSON.stringify(json) });
      State.workflows[wf.id] = wf;
      Sidebar.renderWorkflowList();
      Sidebar.selectWorkflow(wf.id);
      UI.toast(`Loaded ${json.name}`, 'success');
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  async validate() {
    if (!State.selectedWorkflowId) return;
    try {
      const result = await API.fetch(`/workflows/${State.selectedWorkflowId}/validate`, { method: 'POST' });
      const box = document.getElementById('validation-box');
      if (result.valid) {
        box.innerHTML = '<div class="validation-result valid">Valid DAG</div>';
      } else {
        box.innerHTML = `<div class="validation-result invalid">
          Invalid:<ul>${result.errors.map(e => '<li>' + UI.esc(e) + '</li>').join('')}</ul>
        </div>`;
      }
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },
};
