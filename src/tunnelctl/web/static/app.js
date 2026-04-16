// tunnelctl web UI

const API = '';

async function fetchJSON(url) {
    const resp = await fetch(API + url);
    return resp.json();
}

async function postJSON(url, data) {
    const resp = await fetch(API + url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data),
    });
    return resp.json();
}

async function deleteJSON(url) {
    const resp = await fetch(API + url, {method: 'DELETE'});
    return resp.json();
}

// Dashboard: poll statuses
async function refreshStatus() {
    const el = document.getElementById('status-table-body');
    if (!el) return;

    try {
        const statuses = await fetchJSON('/api/status');
        el.innerHTML = statuses.map(s => {
            const lastConn = s.last_connected
                ? new Date(s.last_connected * 1000).toLocaleString()
                : '-';
            return `<tr>
                <td>${s.tunnel}</td>
                <td>${s.endpoint}</td>
                <td><span class="status-badge status-${s.status}">${s.status}</span></td>
                <td>${lastConn}</td>
                <td>${s.error || ''}</td>
            </tr>`;
        }).join('');

        if (statuses.length === 0) {
            el.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-dim)">No tunnels found</td></tr>';
        }
    } catch (e) {
        el.innerHTML = '<tr><td colspan="5" style="color:var(--red)">Failed to fetch status</td></tr>';
    }
}

// Tunnels page
async function refreshTunnels() {
    const el = document.getElementById('tunnels-table-body');
    if (!el) return;

    try {
        const tunnels = await fetchJSON('/api/tunnels');
        el.innerHTML = tunnels.map(t => {
            const eps = (t.endpoints && t.endpoints.length) ? t.endpoints.join(', ') : 'all';
            return `<tr>
                <td>${t.name}</td>
                <td>${t.internal_host}:${t.internal_port}</td>
                <td>${t.remote_port}</td>
                <td>${t.protocol}</td>
                <td>${eps}</td>
                <td>${t.subdomain || '-'}</td>
                <td><button class="btn btn-danger btn-sm" onclick="removeTunnel('${t.name}')">Remove</button></td>
            </tr>`;
        }).join('');
    } catch (e) {
        console.error('Failed to fetch tunnels', e);
    }
}

async function addTunnel(event) {
    event.preventDefault();
    const form = event.target;
    const data = {
        name: form.name.value,
        internal_host: form.internal_host.value,
        internal_port: parseInt(form.internal_port.value),
        remote_port: parseInt(form.remote_port.value),
        protocol: form.protocol.value,
        endpoints: form.endpoints.value ? form.endpoints.value.split(',').map(s => s.trim()) : [],
        subdomain: form.subdomain.value || null,
    };

    const result = await postJSON('/api/tunnels', data);
    document.getElementById('tunnel-msg').textContent = result.message || JSON.stringify(result);
    form.reset();
    refreshTunnels();
}

async function removeTunnel(name) {
    if (!confirm(`Remove tunnel "${name}"?`)) return;
    const result = await deleteJSON(`/api/tunnels/${name}`);
    document.getElementById('tunnel-msg').textContent = result.message || JSON.stringify(result);
    refreshTunnels();
}

// Logs page
async function refreshLogs() {
    const el = document.getElementById('logs-container');
    if (!el) return;

    try {
        const logs = await fetchJSON('/api/logs?limit=100');
        el.innerHTML = logs.reverse().map(log => {
            const dt = new Date(log.timestamp * 1000);
            const time = dt.toLocaleTimeString();
            const tunnel = log.tunnel ? ` [${log.tunnel}]` : '';
            return `<div class="log-entry">
                <span class="time">${time}</span>
                <span class="level-${log.level}">${log.level.padStart(7)}</span>
                ${tunnel} ${log.message}
            </div>`;
        }).join('');
    } catch (e) {
        el.innerHTML = '<div style="color:var(--red)">Failed to fetch logs</div>';
    }
}

// Auto-refresh based on page
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('status-table-body')) {
        refreshStatus();
        setInterval(refreshStatus, 5000);
    }
    if (document.getElementById('tunnels-table-body')) {
        refreshTunnels();
    }
    if (document.getElementById('logs-container')) {
        refreshLogs();
        setInterval(refreshLogs, 10000);
    }
});
