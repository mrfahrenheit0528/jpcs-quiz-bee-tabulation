/* =========================================================
   JPCS Tabulation — Motion Layer (behaviour)
   ========================================================= */
(function () {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* --- Button loading state on form submit ---
       Runs after confirm() handlers, so a cancelled confirm never shows a spinner. */
    document.addEventListener('submit', function (e) {
        const btn = e.submitter;
        if (!btn || e.defaultPrevented || btn.classList.contains('is-loading')) return;
        // Defer so the button's own value is still sent with the form
        setTimeout(function () {
            btn.classList.add('is-loading');
            btn.insertAdjacentHTML('afterbegin', '<span class="btn-spinner" aria-hidden="true"></span>');
        }, 0);
    });

    /* --- Number tween --- */
    function countTo(el, from, to, duration) {
        if (reduceMotion || isNaN(from) || isNaN(to) || from === to) { el.textContent = to; return; }
        const decimals = (String(to).split('.')[1] || '').length;
        const start = performance.now();
        function frame(now) {
            const t = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - t, 3);
            el.textContent = (from + (to - from) * eased).toFixed(decimals);
            if (t < 1) requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    }

    /* --- Live region refresh with FLIP row reordering ---
       <div data-live-refresh="3000"> is re-fetched in the background and swapped in place.
       Rows tagged data-flip-key slide from their old position to their new one;
       elements tagged .score-value count from their old number to the new one. */
    function initLiveRegion(region) {
        const id = region.id;
        let busy = false;

        // Don't swap the DOM out from under the user mid-interaction
        function userIsBusy() {
            const active = document.activeElement;
            return region.querySelector('.is-loading') ||
                   document.querySelector('.modal.show') ||
                   (active && region.contains(active) && /^(INPUT|SELECT|TEXTAREA)$/.test(active.tagName));
        }

        async function refresh() {
            if (busy || document.hidden || userIsBusy()) return;
            busy = true;
            try {
                const res = await fetch(window.location.href, { cache: 'no-store', credentials: 'same-origin' });
                if (!res.ok) return;
                const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
                const fresh = doc.getElementById(id);
                if (!fresh || fresh.innerHTML === region.innerHTML || userIsBusy()) return;
                swap(region, fresh);
            } catch (err) {
                // Network hiccup: keep the current board and try again next tick
            } finally {
                busy = false;
            }
        }

        // Re-read the interval each tick: the server can switch it (e.g. idle vs. live event)
        (function loop() {
            setTimeout(function () { refresh().then(loop); }, parseInt(region.dataset.liveRefresh, 10) || 3000);
        })();
        document.addEventListener('visibilitychange', refresh);
    }

    function swap(region, fresh) {
        // FIRST: record where every keyed row currently is, and its score
        const before = {};
        region.querySelectorAll('[data-flip-key]').forEach(function (row) {
            const score = row.querySelector('.score-value');
            const bar = row.querySelector('.progress-bar');
            before[row.dataset.flipKey] = {
                top: row.getBoundingClientRect().top,
                score: score ? parseFloat(score.textContent) : NaN,
                barWidth: bar ? bar.style.width : null
            };
        });

        region.classList.add('is-live-updated');
        region.innerHTML = fresh.innerHTML;
        if (fresh.dataset.liveRefresh) region.dataset.liveRefresh = fresh.dataset.liveRefresh;

        // LAST + INVERT + PLAY
        region.querySelectorAll('[data-flip-key]').forEach(function (row) {
            const prev = before[row.dataset.flipKey];
            if (!prev) { row.classList.add('anim-pop'); return; }

            const dy = prev.top - row.getBoundingClientRect().top;
            if (dy && !reduceMotion) {
                row.style.transform = 'translateY(' + dy + 'px)';
                row.style.transition = 'none';
                requestAnimationFrame(function () {
                    row.style.transition = 'transform .7s cubic-bezier(.2,.7,.2,1)';
                    row.style.transform = '';
                });
            }

            // Progress bars glide from their old width to the new one
            const bar = row.querySelector('.progress-bar');
            if (bar && prev.barWidth !== null && prev.barWidth !== bar.style.width) {
                const target = bar.style.width;
                bar.style.width = prev.barWidth;
                bar.getBoundingClientRect(); // commit the old width before transitioning
                bar.style.width = target;
            }

            const score = row.querySelector('.score-value');
            if (score) {
                const next = parseFloat(score.textContent);
                if (!isNaN(prev.score) && next !== prev.score) {
                    countTo(score, prev.score, next, 800);
                    const cell = score.closest('td');
                    cell.classList.add('score-changed');
                    cell.addEventListener('animationend', function done(e) {
                        if (e.target !== cell) return; // ignore the inner number's pop
                        cell.classList.remove('score-changed');
                        cell.removeEventListener('animationend', done);
                    });
                }
            }
        });
    }

    /* --- Confetti burst (used on final results) --- */
    function confetti(duration) {
        if (reduceMotion) return;
        const canvas = document.createElement('canvas');
        canvas.id = 'confetti-canvas';
        document.body.appendChild(canvas);
        const ctx = canvas.getContext('2d');
        const colors = ['#800000', '#E35205', '#FFD700', '#C0C0C0', '#CD7F32', '#ffffff'];
        let w, h;
        function resize() { w = canvas.width = innerWidth; h = canvas.height = innerHeight; }
        resize();
        addEventListener('resize', resize);

        const pieces = Array.from({ length: 160 }, function () {
            return {
                x: Math.random() * w,
                y: -20 - Math.random() * h * 0.6,
                size: 6 + Math.random() * 6,
                color: colors[Math.floor(Math.random() * colors.length)],
                vy: 2 + Math.random() * 3,
                vx: -1.5 + Math.random() * 3,
                rot: Math.random() * Math.PI,
                vr: -0.15 + Math.random() * 0.3
            };
        });

        const end = performance.now() + duration;
        (function frame(now) {
            ctx.clearRect(0, 0, w, h);
            const fading = now > end;
            let alive = 0;
            pieces.forEach(function (p) {
                p.x += p.vx; p.y += p.vy; p.rot += p.vr;
                if (!fading && p.y > h) { p.y = -20; p.x = Math.random() * w; }
                if (p.y <= h) alive++;
                ctx.save();
                ctx.translate(p.x, p.y);
                ctx.rotate(p.rot);
                ctx.fillStyle = p.color;
                ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
                ctx.restore();
            });
            if (alive) requestAnimationFrame(frame);
            else { canvas.remove(); removeEventListener('resize', resize); }
        })(performance.now());
    }

    /* --- Count-up on first paint for [data-count-up] --- */
    function initCountUps() {
        document.querySelectorAll('[data-count-up]').forEach(function (el) {
            const target = parseFloat(el.textContent);
            if (!isNaN(target)) countTo(el, 0, target, 1200);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-live-refresh]').forEach(initLiveRegion);
        initCountUps();
        if (document.querySelector('[data-confetti]')) setTimeout(function () { confetti(3500); }, 600);
    });

    window.JPCSMotion = { countTo: countTo, confetti: confetti };
})();
