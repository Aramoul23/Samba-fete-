/* ═══════════════════════════════════════════════════════════════════
   Samba Fête — HTMX-enhanced interactions
   ═══════════════════════════════════════════════════════════════════ */

// ── FullCalendar Integration ────────────────────────────────────────
function initCalendar(containerId, eventsUrl, serverMap, serverUrlMap) {
    const container = document.getElementById(containerId);
    if (!container || typeof FullCalendar === 'undefined') return;

    const dateStatusMap = {};
    const dateUrlMap = {};

    Object.assign(dateStatusMap, serverMap || {});
    Object.assign(dateUrlMap, serverUrlMap || {});

    const calendar = new FullCalendar.Calendar(container, {
        initialView: 'dayGridMonth',
        locale: 'fr',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,listMonth'
        },
        events: function(fetchInfo, successCallback, failureCallback) {
            fetch(eventsUrl + '?start=' + fetchInfo.startStr + '&end=' + fetchInfo.endStr)
                .then(r => {
                    if (!r.ok) {
                        console.warn('Calendar events returned', r.status, '- rendering without colors');
                        successCallback([]);
                        return null;
                    }
                    return r.json();
                })
                .then(events => {
                    if (events === null) return; // already handled above

                    Object.keys(dateStatusMap).forEach(k => delete dateStatusMap[k]);
                    Object.keys(dateUrlMap).forEach(k => delete dateUrlMap[k]);

                    events.forEach(function(ev) {
                        if (ev.start && ev.extendedProps && ev.extendedProps.status) {
                            dateStatusMap[ev.start] = ev.extendedProps.status;
                            dateUrlMap[ev.start] = ev.url;
                        }
                    });

                    successCallback([]);
                })
                .catch(err => {
                    console.error('Calendar fetch failed:', err);
                    successCallback([]);
                });
        },
        dayCellDidMount: function(info) {
            const moreLink = info.el.querySelector('.fc-daygrid-more-link');
            if (moreLink) moreLink.remove();

            const dateStr = info.date.toISOString().slice(0, 10);
            const status = dateStatusMap[dateStr];

            if (status) {
                info.el.style.cursor = 'pointer';
                info.el.addEventListener('click', function() {
                    const url = dateUrlMap[dateStr];
                    if (url) window.location.href = url;
                });

                if (status === 'confirmé' || status === 'terminé') {
                    info.el.style.backgroundColor = '#ef476f';
                    info.el.style.color = '#ffffff';
                } else if (status === 'en attente') {
                    info.el.style.backgroundColor = '#ffd166';
                    info.el.style.color = '#333333';
                } else if (status === 'changé de date') {
                    info.el.style.backgroundColor = '#118ab2';
                    info.el.style.color = '#ffffff';
                }

                const dayNumber = info.el.querySelector('.fc-daygrid-day-number');
                if (dayNumber) dayNumber.style.color = info.el.style.color;
            }
        },
        dateClick: function(info) {
            const url = dateUrlMap[info.dateStr];
            if (url) {
                window.location.href = url;
            } else {
                window.location.href = '/evenement/nouveau?date=' + info.dateStr;
            }
        },
        height: 'auto',
        dayMaxEvents: false,
        navLinks: true,
        nowIndicator: true,
    });

    calendar.render();
    return calendar;
}

// ── Live Search ─────────────────────────────────────────────────────
function initLiveSearch(inputId, targetUrl, containerId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    let timeout;
    input.addEventListener('input', function() {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            const q = input.value.trim();
            const url = q ? `${targetUrl}?q=${encodeURIComponent(q)}` : targetUrl;
            htmx.ajax('GET', url, {target: `#${containerId}`, swap: 'innerHTML'});
        }, 300);
    });
}

// ── PDF Preview Modal ───────────────────────────────────────────────
function previewPDF(url, title) {
    // Create modal
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.7); z-index: 10000;
        display: flex; align-items: center; justify-content: center;
        padding: 20px;
    `;

    const content = document.createElement('div');
    content.style.cssText = `
        background: white; border-radius: 16px; width: 90%; max-width: 900px;
        height: 85vh; display: flex; flex-direction: column; overflow: hidden;
        box-shadow: 0 25px 50px rgba(0,0,0,0.3);
    `;

    content.innerHTML = `
        <div style="padding: 16px 20px; display: flex; justify-content: space-between;
                    align-items: center; border-bottom: 1px solid #eee;">
            <h3 style="margin: 0; font-size: 1.1rem;">${title || 'Aperçu PDF'}</h3>
            <div style="display: flex; gap: 8px;">
                <a href="${url}" download class="btn btn-sm btn-success">
                    <i class="fas fa-download"></i> Télécharger
                </a>
                <button onclick="this.closest('[style*=fixed]').remove()"
                        class="btn btn-sm btn-outline-secondary">
                    <i class="fas fa-times"></i> Fermer
                </button>
            </div>
        </div>
        <iframe src="${url}" style="flex: 1; border: none;"></iframe>
    `;

    modal.appendChild(content);
    document.body.appendChild(modal);

    // Close on overlay click
    modal.addEventListener('click', function(e) {
        if (e.target === modal) modal.remove();
    });

    // Close on Escape
    document.addEventListener('keydown', function handler(e) {
        if (e.key === 'Escape') {
            modal.remove();
            document.removeEventListener('keydown', handler);
        }
    });
}

// ── HTMX Event Handlers ─────────────────────────────────────────────
document.addEventListener('htmx:beforeRequest', function(e) {
    // Show loading spinner on the triggering element
    const el = e.detail.elt;
    if (el.tagName === 'BUTTON' || el.classList.contains('btn')) {
        el.classList.add('btn-loading');
    }
});

document.addEventListener('htmx:afterRequest', function(e) {
    const el = e.detail.elt;
    el.classList.remove('btn-loading');

    // Flash messages for HTMX responses
    if (e.detail.xhr.getResponseHeader('X-Flash-Message')) {
        const msg = e.detail.xhr.getResponseHeader('X-Flash-Message');
        const cat = e.detail.xhr.getResponseHeader('X-Flash-Category') || 'info';
        showFlash(msg, cat);
    }
});

// ── Flash Messages ──────────────────────────────────────────────────
function showFlash(message, category) {
    const container = document.querySelector('.container-fluid.px-4');
    if (!container) return;

    const icons = {
        success: 'check-circle', danger: 'exclamation-circle',
        warning: 'exclamation-triangle', info: 'info-circle'
    };

    const alert = document.createElement('div');
    alert.className = `alert alert-${category} alert-dismissible fade show mt-3`;
    alert.innerHTML = `
        <i class="fas fa-${icons[category] || 'info-circle'} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    container.insertBefore(alert, container.firstChild);

    // Auto-dismiss after 5s
    setTimeout(() => alert.remove(), 5000);
}

// ── Sidebar Toggle ──────────────────────────────────────────────────
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.querySelector('.sidebar-overlay').classList.toggle('active');
}

// ── Auto-inject CSRF ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    // Flatpickr date inputs with calendar event coloring
    if (typeof flatpickr !== 'undefined') {
        let calendarEvents = {};

        function loadCalendarEvents(fp) {
            const d = fp.currentYear ? new Date(fp.currentYear, fp.currentMonth) : new Date();
            fetch(`/api/calendar-events?year=${d.getFullYear()}&month=${d.getMonth() + 1}&include_cancelled=true`)
                .then(r => r.json())
                .then(events => {
                    calendarEvents = {};
                    events.forEach(ev => {
                        const d = ev.start;
                        const status = ev.extendedProps?.status;
                        if (d && status) calendarEvents[d] = status;
                    });
                    fp.redraw();
                })
                .catch(() => { calendarEvents = {}; });
        }

        flatpickr('input[type="date"], input[name="expense_date"]', {
            dateFormat: 'Y-m-d',
            locale: 'fr',
            allowInput: true,
            closeOnSelect: true,
            onReady: function(selectedDates, dateStr, instance) {
                loadCalendarEvents(instance);
            },
            onMonthChange: function(selectedDates, dateStr, instance) {
                loadCalendarEvents(instance);
            },
            onDayCreate: function(dObj, dStr, fp, dayElem) {
                if (dayElem.classList.contains('flatpickr-disabled') ||
                    dayElem.classList.contains('prevMonthDay') ||
                    dayElem.classList.contains('nextMonthDay')) return;

                const date = dayElem.dateObj;
                const dateStr = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
                const status = calendarEvents[dateStr];

                if (status === 'confirmé' || status === 'terminé') {
                    dayElem.style.background = 'rgba(6, 214, 160, 0.15)';
                    dayElem.style.color = '#06d6a0';
                    dayElem.style.fontWeight = '700';
                    dayElem.title = `${dateStr} — ${status}`;
                } else if (status === 'en attente') {
                    dayElem.style.background = 'rgba(255, 209, 102, 0.15)';
                    dayElem.style.color = '#ffd166';
                    dayElem.style.fontWeight = '700';
                    dayElem.title = `${dateStr} — ${status}`;
                } else if (status === 'annulé') {
                    dayElem.style.background = 'rgba(255, 100, 100, 0.10)';
                    dayElem.style.color = '#ef476f';
                    dayElem.title = `${dateStr} — ${status}`;
                }
            },
        });
    }
});
