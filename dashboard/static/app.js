const REFRESH_MS = 15000;

const charts = {};
const statusCharts = {};
let recentEvents = [];
let refreshTimer = null;
const TICK_STYLE = { color: '#64748b' };
const GRID_STYLE = { color: 'rgba(100,116,139,0.15)' };

function chartOptions(overrides = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: { legend: { labels: { color: '#94a3b8' } } },
    scales: {
      x: { ticks: { ...TICK_STYLE }, grid: { ...GRID_STYLE }, beginAtZero: true },
      y: { ticks: { ...TICK_STYLE }, grid: { ...GRID_STYLE }, beginAtZero: true },
    },
    ...overrides,
  };
}

const COLORS = [
  '#38bdf8', '#818cf8', '#34d399', '#fbbf24', '#f472b6', '#fb923c', '#a78bfa',
];

function animateValue(el, newVal, suffix = '') {
  const current = parseFloat(el.dataset.value) || 0;
  const target = parseFloat(newVal) || 0;
  el.dataset.value = target;
  const duration = 400;
  const start = performance.now();
  function step(now) {
    const t = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    const val = current + (target - current) * eased;
    el.textContent = Number.isInteger(target)
      ? Math.round(val).toLocaleString() + suffix
      : val.toFixed(1) + suffix;
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function statusBadge(code) {
  const c = parseInt(code);
  let cls = 'bg-slate-600';
  if (c >= 500) cls = 'bg-red-500/80';
  else if (c >= 400) cls = 'bg-amber-500/80';
  else if (c >= 200) cls = 'bg-emerald-500/80';
  return `<span class="inline-block px-2 py-0.5 rounded text-xs font-medium text-white ${cls}">${c}</span>`;
}

function formatChartTime(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  } catch {
    return ts;
  }
}

function formatTime(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    return d.toLocaleString();
  } catch {
    return ts;
  }
}

function startDashboard() {
  if (refreshTimer) clearInterval(refreshTimer);
  fetchDashboard();
  refreshTimer = setInterval(fetchDashboard, REFRESH_MS);
}

function statusColor(code) {
  if (code >= 500) return '#ef4444';
  if (code >= 400) return '#f59e0b';
  return '#22c55e';
}

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  layout: { padding: 0 },
  plugins: {
    legend: {
      position: 'right',
      align: 'center',
      labels: { color: '#94a3b8', boxWidth: 8, font: { size: 9 }, padding: 6 },
    },
  },
};

function updateStatusCharts(rows) {
  const container = document.getElementById('statusChartsGrid');
  const grouped = {};
  rows.forEach((r) => {
    if (!grouped[r.endpoint]) grouped[r.endpoint] = [];
    grouped[r.endpoint].push(r);
  });

  const endpoints = Object.keys(grouped).sort();

  Object.keys(statusCharts).forEach((ep) => {
    if (!endpoints.includes(ep)) {
      statusCharts[ep].destroy();
      delete statusCharts[ep];
    }
  });

  endpoints.forEach((ep) => {
    let wrapper = container.querySelector(`[data-endpoint="${ep}"]`);
    if (!wrapper) {
      wrapper = document.createElement('div');
      wrapper.className = 'status-chart-cell glass rounded-lg p-2 flex flex-col min-h-0';
      wrapper.dataset.endpoint = ep;
      wrapper.innerHTML = `
        <p class="text-xs font-mono text-slate-400 mb-1 text-center truncate shrink-0" title="${ep}">${ep}</p>
        <div class="status-mini-chart"><canvas></canvas></div>
      `;
      container.appendChild(wrapper);
    }

    const items = grouped[ep].sort((a, b) => a.status_code - b.status_code);
    const labels = items.map((r) => String(r.status_code));
    const counts = items.map((r) => r.count);
    const colors = items.map((r) => statusColor(r.status_code));
    const canvas = wrapper.querySelector('canvas');

    if (statusCharts[ep]) {
      statusCharts[ep].data.labels = labels;
      statusCharts[ep].data.datasets[0].data = counts;
      statusCharts[ep].data.datasets[0].backgroundColor = colors;
      statusCharts[ep].update('none');
    } else {
      statusCharts[ep] = new Chart(canvas, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: counts, backgroundColor: colors, borderWidth: 0 }] },
        options: doughnutOptions,
      });
    }
  });

  [...container.children].forEach((child) => {
    const ep = child.dataset.endpoint;
    if (!endpoints.includes(ep)) {
      if (statusCharts[ep]) {
        statusCharts[ep].destroy();
        delete statusCharts[ep];
      }
      child.remove();
    }
  });
}

function initCharts() {
  charts.timeline = new Chart(document.getElementById('timelineChart'), {
    type: 'line',
    data: { labels: [], datasets: [{ label: 'Requests', data: [], borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,0.1)', fill: true, tension: 0.3 }] },
    options: chartOptions({
      scales: {
        x: { ticks: { ...TICK_STYLE, maxRotation: 45 }, grid: { ...GRID_STYLE } },
        y: { ticks: { ...TICK_STYLE }, grid: { ...GRID_STYLE }, beginAtZero: true },
      },
    }),
  });

  charts.endpoint = new Chart(document.getElementById('endpointChart'), {
    type: 'bar',
    data: { labels: [], datasets: [{ label: 'Count', data: [], backgroundColor: COLORS }] },
    options: chartOptions(),
  });

  charts.latency = new Chart(document.getElementById('latencyChart'), {
    type: 'bar',
    data: { labels: [], datasets: [{ label: 'Avg ms', data: [], backgroundColor: '#34d399' }] },
    options: chartOptions({
      scales: {
        x: { ticks: { ...TICK_STYLE, maxRotation: 45 }, grid: { ...GRID_STYLE } },
        y: {
          ticks: { ...TICK_STYLE, callback: (v) => `${v} ms` },
          grid: { ...GRID_STYLE },
          beginAtZero: true,
        },
      },
    }),
  });
}

function updateCharts(data) {
  if (!charts.timeline) return;
  const tl = data.timeline || [];
  charts.timeline.data.labels = tl.map((r) => formatChartTime(r.time));
  charts.timeline.data.datasets[0].data = tl.map((r) => r.count);
  charts.timeline.update('none');

  const ep = data.by_endpoint || [];
  charts.endpoint.data.labels = ep.map((r) => r.endpoint);
  charts.endpoint.data.datasets[0].data = ep.map((r) => r.count);
  charts.endpoint.data.datasets[0].backgroundColor = ep.map((_, i) => COLORS[i % COLORS.length]);
  charts.endpoint.update('none');

  const lat = data.latency || [];
  charts.latency.data.labels = lat.map((r) => r.endpoint);
  charts.latency.data.datasets[0].data = lat.map((r) => Number(r.avg_ms) || 0);
  charts.latency.data.datasets[0].backgroundColor = lat.map((_, i) => COLORS[i % COLORS.length]);
  charts.latency.update('none');

  updateStatusCharts(data.status_by_endpoint || []);
}

function updateKPIs(summary) {
  animateValue(document.getElementById('kpiTotal'), summary.total || 0);
  animateValue(document.getElementById('kpiErrorRate'), summary.error_rate || 0, '%');
  animateValue(document.getElementById('kpiLatency'), summary.avg_latency || 0, ' ms');
  animateValue(document.getElementById('kpiFailedLogins'), summary.failed_logins || 0);
}

function fieldCell(label, value) {
  return `
    <div class="glass rounded-lg px-3 py-2">
      <p class="text-slate-500 text-xs mb-1">${label}</p>
      <p class="text-slate-200 break-all">${value || '—'}</p>
    </div>
  `;
}

function openEventModal(event) {
  const modal = document.getElementById('eventModal');
  document.getElementById('modalSubtitle').textContent =
    `${event.method || '—'} ${event.endpoint || '—'} · ${formatTime(event.timestamp)}`;

  const fields = [
    ['Timestamp', formatTime(event.timestamp)],
    ['Service', event.service],
    ['Endpoint', event.endpoint],
    ['Method', event.method],
    ['Status', event.status_code],
    ['Latency', `${event.response_time_ms} ms`],
    ['IP', event.ip],
    ['User ID', event.user_id],
  ];
  document.getElementById('modalFields').innerHTML =
    fields.map(([label, value]) => fieldCell(label, value)).join('');

  const splunkFields = Object.entries(event.splunk || {});
  document.getElementById('modalSplunk').innerHTML = splunkFields.length
    ? splunkFields.map(([label, value]) => fieldCell(label, value)).join('')
    : fieldCell('Info', 'No Splunk metadata');

  const rawText = event.raw || JSON.stringify(event.parsed || {}, null, 2);
  try {
    document.getElementById('modalRaw').textContent = event.raw
      ? JSON.stringify(JSON.parse(event.raw), null, 2)
      : JSON.stringify(event.parsed || {}, null, 2);
  } catch {
    document.getElementById('modalRaw').textContent = rawText;
  }

  document.getElementById('modalFull').textContent = JSON.stringify(event, null, 2);
  modal.classList.remove('hidden');
  document.body.classList.add('overflow-hidden');
}

function closeEventModal() {
  document.getElementById('eventModal').classList.add('hidden');
  document.body.classList.remove('overflow-hidden');
}

function updateTable(events) {
  recentEvents = events || [];
  const tbody = document.getElementById('eventsBody');
  if (!recentEvents.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-slate-500">No events in selected range</td></tr>';
    return;
  }
  tbody.innerHTML = recentEvents.map((e, i) => `
    <tr class="event-row border-b border-slate-800/50 transition-colors" data-index="${i}" title="View full event">
      <td class="py-2.5 pr-4 text-slate-400 text-xs whitespace-nowrap">${formatTime(e.timestamp)}</td>
      <td class="py-2.5 pr-4 font-mono text-xs">${e.endpoint || '—'}</td>
      <td class="py-2.5 pr-4">${e.method || '—'}</td>
      <td class="py-2.5 pr-4">${statusBadge(e.status_code)}</td>
      <td class="py-2.5 pr-4">${e.response_time_ms} ms</td>
      <td class="py-2.5 pr-4 font-mono text-xs text-slate-400">${e.ip || '—'}</td>
      <td class="py-2.5 text-slate-400">${e.user_id || '—'}</td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.event-row').forEach((row) => {
    row.addEventListener('click', () => {
      const index = Number(row.dataset.index);
      if (recentEvents[index]) openEventModal(recentEvents[index]);
    });
  });
}

function showError(msg) {
  const banner = document.getElementById('errorBanner');
  if (msg) {
    banner.textContent = msg;
    banner.classList.remove('hidden');
    document.getElementById('liveDot').classList.replace('bg-emerald-400', 'bg-red-400');
    document.getElementById('liveLabel').textContent = 'Disconnected';
  } else {
    banner.classList.add('hidden');
    document.getElementById('liveDot').classList.replace('bg-red-400', 'bg-emerald-400');
    document.getElementById('liveLabel').textContent = 'Live';
  }
}

async function fetchDashboard() {
  const range = document.getElementById('rangeSelect').value;
  try {
    const res = await fetch('/api/dashboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ range }),
    });
    const data = await res.json();
    if (!data.ok && data.error) {
      showError(`Splunk error: ${data.error}`);
    } else {
      showError(null);
    }
    updateKPIs(data.summary || {});
    updateCharts(data);
    updateTable(data.recent || []);
    document.getElementById('lastUpdated').textContent =
      'Updated ' + new Date().toLocaleTimeString();
  } catch (err) {
    showError(`Failed to fetch dashboard: ${err.message}`);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  try {
    initCharts();
  } catch (err) {
    console.error('Chart init failed:', err);
    showError(`Chart library failed to load: ${err.message}`);
  }
  document.getElementById('rangeSelect').addEventListener('change', fetchDashboard);
  document.getElementById('closeModal').addEventListener('click', closeEventModal);
  document.getElementById('eventModal').addEventListener('click', (e) => {
    if (e.target.id === 'eventModal') closeEventModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeEventModal();
  });
  startDashboard();
});
