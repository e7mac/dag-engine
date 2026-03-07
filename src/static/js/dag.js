const DAG = {
  draw(wf, trace = null) {
    State.lastDAGArgs = { wf, trace };

    // Set up canvas with device pixel ratio
    const canvas = document.getElementById('dag-canvas');
    const wrap = document.getElementById('canvas-wrap');
    const dpr = window.devicePixelRatio || 1;

    canvas.width = wrap.clientWidth * dpr;
    canvas.height = wrap.clientHeight * dpr;
    canvas.style.width = wrap.clientWidth + 'px';
    canvas.style.height = wrap.clientHeight + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const W = wrap.clientWidth;
    const H = wrap.clientHeight;
    ctx.clearRect(0, 0, W, H);

    const nodes = wf.nodes;
    const nodeIds = Object.keys(nodes);
    if (nodeIds.length === 0) return;

    // --- Build adjacency for layout ---
    const children = {};
    const parents = {};
    nodeIds.forEach(id => {
      children[id] = [];
      parents[id] = [];
    });

    nodeIds.forEach(id => {
      const n = nodes[id];

      if (n.type === 'third_party' && n.next) {
        children[id].push({ target: n.next, label: '' });
        parents[n.next].push(id);
      } else if (n.type === 'branch') {
        (n.edges || []).forEach(e => {
          children[id].push({ target: e.next, label: e.label });
          parents[e.next].push(id);
        });
        if (n.default_next) {
          children[id].push({ target: n.default_next, label: 'default' });
          parents[n.default_next].push(id);
        }
      }
    });

    // --- Topological layering via BFS from start_node_id ---
    const layers = [];
    const layerOf = {};
    const visited = new Set();
    let queue = [wf.start_node_id];
    visited.add(wf.start_node_id);

    while (queue.length > 0) {
      layers.push(queue);
      queue.forEach(id => {
        layerOf[id] = layers.length - 1;
      });

      const next = [];
      queue.forEach(id => {
        children[id].forEach(({ target }) => {
          if (!visited.has(target)) {
            visited.add(target);
            next.push(target);
          }
        });
      });
      queue = next;
    }

    // Add any orphans
    nodeIds.forEach(id => {
      if (!visited.has(id)) {
        layers.push([id]);
        layerOf[id] = layers.length - 1;
      }
    });

    // --- Position nodes ---
    const nodeW = 150;
    const nodeH = 40;
    const layerGap = 80;
    const nodeGap = 30;
    const totalH = layers.length * nodeH + (layers.length - 1) * layerGap;
    const startY = Math.max(30, (H - totalH) / 2);

    const pos = {};
    layers.forEach((layer, li) => {
      const totalW = layer.length * nodeW + (layer.length - 1) * nodeGap;
      const startX = (W - totalW) / 2;
      layer.forEach((id, ni) => {
        pos[id] = {
          x: startX + ni * (nodeW + nodeGap),
          y: startY + li * (nodeH + layerGap),
        };
      });
    });

    // --- Build trace lookup ---
    const traceLookup = {};
    if (trace && trace.nodes) {
      trace.nodes.forEach(n => {
        traceLookup[n.node_id] = n;
      });
    }

    // --- Draw edges ---
    ctx.lineWidth = 1.5;

    nodeIds.forEach(id => {
      const from = pos[id];
      if (!from) return;

      children[id].forEach(({ target, label }) => {
        const to = pos[target];
        if (!to) return;

        const fromX = from.x + nodeW / 2;
        const fromY = from.y + nodeH;
        const toX = to.x + nodeW / 2;
        const toY = to.y;

        // Check if this edge was taken in trace
        const traceNode = traceLookup[id];
        const edgeTaken = traceNode && (
          (traceNode.branch_taken === label && label) ||
          (nodes[id].type === 'third_party' && traceNode.status === 'success')
        );

        ctx.strokeStyle = edgeTaken ? '#6c8cff' : '#3a3f52';
        ctx.lineWidth = edgeTaken ? 2.5 : 1.5;

        // Curved edge
        ctx.beginPath();
        ctx.moveTo(fromX, fromY);
        const midY = (fromY + toY) / 2;
        ctx.bezierCurveTo(fromX, midY, toX, midY, toX, toY);
        ctx.stroke();

        // Arrow
        const angle = Math.atan2(toY - midY, toX - toX) || Math.PI / 2;
        const arrowSize = 6;
        ctx.fillStyle = ctx.strokeStyle;
        ctx.beginPath();
        ctx.moveTo(toX, toY);
        ctx.lineTo(
          toX - arrowSize * Math.cos(angle - 0.4),
          toY - arrowSize * Math.sin(angle - 0.4)
        );
        ctx.lineTo(
          toX - arrowSize * Math.cos(angle + 0.4),
          toY - arrowSize * Math.sin(angle + 0.4)
        );
        ctx.fill();

        // Edge label
        if (label) {
          ctx.font = '10px -apple-system, sans-serif';
          ctx.fillStyle = '#8b90a0';
          const lx = (fromX + toX) / 2 + (fromX === toX ? 12 : 0);
          const ly = midY - 4;
          ctx.fillText(label, lx, ly);
        }
      });
    });

    // --- Draw nodes ---
    nodeIds.forEach(id => {
      const p = pos[id];
      if (!p) return;

      const n = nodes[id];
      const tn = traceLookup[id];

      // Node color by type
      let bg, border;
      if (n.type === 'third_party') {
        bg = '#1a2744';
        border = '#3b6cf5';
      } else if (n.type === 'branch') {
        bg = '#2a2314';
        border = '#d4a017';
      } else {
        bg = '#142a1a';
        border = '#3cb371';
      }

      // Override with trace status color
      if (tn) {
        if (tn.status === 'success') {
          bg = '#0f2a1a';
          border = '#4ade80';
        } else if (tn.status === 'failed') {
          bg = '#2a0f0f';
          border = '#f87171';
        } else if (tn.status === 'running') {
          bg = '#2a2314';
          border = '#fbbf24';
        }
      }

      // Rounded rect helper
      const r = 8;
      const drawRoundedRect = () => {
        ctx.beginPath();
        ctx.moveTo(p.x + r, p.y);
        ctx.lineTo(p.x + nodeW - r, p.y);
        ctx.quadraticCurveTo(p.x + nodeW, p.y, p.x + nodeW, p.y + r);
        ctx.lineTo(p.x + nodeW, p.y + nodeH - r);
        ctx.quadraticCurveTo(p.x + nodeW, p.y + nodeH, p.x + nodeW - r, p.y + nodeH);
        ctx.lineTo(p.x + r, p.y + nodeH);
        ctx.quadraticCurveTo(p.x, p.y + nodeH, p.x, p.y + nodeH - r);
        ctx.lineTo(p.x, p.y + r);
        ctx.quadraticCurveTo(p.x, p.y, p.x + r, p.y);
        ctx.closePath();
      };

      // Fill and stroke node
      ctx.fillStyle = bg;
      ctx.strokeStyle = border;
      ctx.lineWidth = 1.5;
      drawRoundedRect();
      ctx.fill();
      ctx.stroke();

      // Highlight glow on hover
      if (State.highlightedNodeId === id) {
        ctx.save();
        ctx.shadowColor = '#6c8cff';
        ctx.shadowBlur = 18;
        ctx.strokeStyle = '#6c8cff';
        ctx.lineWidth = 2.5;
        drawRoundedRect();
        ctx.stroke();
        ctx.restore();
      }

      // Type icon
      let icon = '';
      if (n.type === 'third_party') {
        icon = '\u25B6';
      } else if (n.type === 'branch') {
        icon = '\u25C7';
      } else {
        icon = '\u25CF';
      }

      ctx.font = '12px -apple-system, sans-serif';
      ctx.fillStyle = border;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(icon, p.x + 10, p.y + nodeH / 2);

      // Label (truncated to fit)
      ctx.fillStyle = '#e1e4ed';
      ctx.font = '12px -apple-system, sans-serif';
      const maxLabelW = nodeW - 32;
      let label = n.label;
      while (ctx.measureText(label).width > maxLabelW && label.length > 3) {
        label = label.slice(0, -1);
      }
      if (label !== n.label) {
        label += '\u2026';
      }
      ctx.fillText(label, p.x + 26, p.y + nodeH / 2);
      ctx.textAlign = 'start';
    });
  },
};
