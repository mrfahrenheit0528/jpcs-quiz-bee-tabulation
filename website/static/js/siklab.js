/* Poll committed scores without navigating away or waiting for round evaluation. */
(() => {
    let etag = null;
    let busy = false;
    let lastSuccess = Date.now();
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function updateBoard(fresh) {
        const current = document.getElementById('siklab-board');
        // Capture each participant's visual position, including any ongoing slide.
        const positions = new Map();
        if (!reducedMotion.matches) {
            current.querySelectorAll('[data-school-id]').forEach(row => {
                positions.set(row.dataset.schoolId, row.getBoundingClientRect().top);
            });
        }
        const scroller = current.querySelector('.table-responsive');
        const scrollLeft = scroller ? scroller.scrollLeft : 0;
        current.replaceWith(fresh);
        const nextScroller = fresh.querySelector('.table-responsive');
        if (nextScroller) nextScroller.scrollLeft = scrollLeft;

        // Move from the previous position to the new rank without shifting layout.
        const moves = [];
        fresh.querySelectorAll('[data-school-id]').forEach(row => {
            const previous = positions.get(row.dataset.schoolId);
            if (previous === undefined) return;
            const distance = previous - row.getBoundingClientRect().top;
            if (Math.abs(distance) > 1) moves.push({row, distance});
        });
        moves.forEach(({row, distance}) => {
            row.classList.add('rank-moving');
            const animation = row.animate([
                {transform: `translateY(${distance}px)`},
                {transform: 'translateY(0)'}
            ], {duration: 700, easing: 'cubic-bezier(.2,.7,.2,1)'});
            const cleanup = () => row.classList.remove('rank-moving');
            animation.finished.then(cleanup, cleanup);
        });
    }

    function connection() {
        const label = document.getElementById('connection-status');
        if (!label) return;
        const stale = Date.now() - lastSuccess > 10000;
        label.textContent = stale ? 'Connection interrupted · retrying' : 'Updating automatically';
        label.classList.toggle('stale', stale);
    }
    async function refresh() {
        if (busy || document.hidden) return;
        busy = true;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        try {
            const response = await fetch('/siklab/fragment', {
                cache: 'no-cache', signal: controller.signal,
                headers: etag ? {'If-None-Match': etag} : {}
            });
            if (response.status === 304) lastSuccess = Date.now();
            else if (response.ok) {
                const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
                const fresh = doc.getElementById('siklab-board');
                if (!fresh) throw new Error('Missing standings');
                updateBoard(fresh);
                etag = response.headers.get('ETag');
                lastSuccess = Date.now();
            }
        } catch (_) {
            // Retain the last received standings while disconnected.
        } finally {
            clearTimeout(timeout);
            busy = false;
            connection();
        }
    }
    setInterval(refresh, 1000);
    window.addEventListener('online', refresh);
    window.addEventListener('pageshow', refresh);
    document.addEventListener('visibilitychange', refresh);
})();
