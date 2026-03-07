const UI = {
  toast(msg, type = '') {
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
  },

  esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  },

  openRegisterModal() {
    document.getElementById('register-json').value = '';
    document.getElementById('register-error').style.display = 'none';
    document.getElementById('register-modal').style.display = 'flex';
  },

  closeModal(id) {
    document.getElementById(id).style.display = 'none';
  },

  openRunModal(live = false) {
    if (!State.selectedWorkflowId) return;
    document.getElementById('run-sandbox').checked = !live;
    document.getElementById('run-context').value = document.getElementById('context-input').value;
    document.getElementById('run-error').style.display = 'none';
    document.getElementById('run-modal').style.display = 'flex';
  },

  toggleDetail(id) {
    const el = document.getElementById(id);
    const toggle = el.previousElementSibling;
    if (el.style.display === 'none') {
      el.style.display = 'block';
      toggle.textContent = 'Hide details';
    } else {
      el.style.display = 'none';
      toggle.textContent = 'Show details';
    }
  },

  toggleStats() {
    State.statsVisible = !State.statsVisible;
    const panel = document.getElementById('stats-panel');
    const btn = document.getElementById('stats-toggle');
    panel.classList.toggle('visible', State.statsVisible);
    btn.classList.toggle('active', State.statsVisible);
    if (State.statsVisible) API.fetchStats();
  },
};
