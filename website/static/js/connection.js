(function () {
    let target = document.getElementById('qr-hostname').disabled ? 'ip' : 'hostname', previous = '', busy = false;
    const qr = document.getElementById('connection-qr');
    function updateQR() { qr.src = '/admin/generate-qr?target=' + target + '&v=' + Date.now(); }
    document.getElementById('qr-hostname').onclick = () => { target = 'hostname'; updateQR(); };
    document.getElementById('qr-ip').onclick = () => { target = 'ip'; updateQR(); };
    async function refresh() {
        if (busy || document.hidden) return;
        busy = true;
        const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 8000);
        try {
            const res = await fetch('/admin/connection', {cache: 'no-store', signal: controller.signal});
            if (!res.ok || res.redirected) return;
            const info = await res.json();
            const primary = document.getElementById('primary-url');
            const primaryUrl = info.hostname_ready ? info.hostname_url : info.direct_url;
            primary.textContent = primaryUrl || 'LAN address unavailable';
            primary.href = primaryUrl || '#';
            for (const [id, url] of [['hostname-url', info.hostname_url], ['direct-url', info.direct_url]]) {
                const link = document.getElementById(id); link.textContent = url || 'LAN address unavailable'; link.href = url || '#';
            }
            document.getElementById('discovery-status').textContent = info.discovery;
            document.getElementById('qr-ip').disabled = !info.direct_url;
            document.getElementById('qr-hostname').disabled = !info.hostname_ready;
            if (target === 'hostname' && !info.hostname_ready && info.direct_url) target = 'ip';
            if (previous !== JSON.stringify(info)) { previous = JSON.stringify(info); updateQR(); }
        } catch (error) { /* Retain connection information while reconnecting. */ }
        finally { clearTimeout(timer); busy = false; }
    }
    (function poll() { refresh().finally(() => setTimeout(poll, 3000)); })();
    document.addEventListener('visibilitychange', refresh);
})();
