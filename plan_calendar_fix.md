# Plan: FullCalendar Day-Cell Coloring Rewrite

## Problem Analysis

The current implementation has a **race condition** and fights FullCalendar's rendering pipeline:

1. `dateStatusMap` is populated in the `eventSources[0].success` callback, which fires **after** events are fetched — but `dayCellDidMount` runs during initial render **before** the map has data. Cells never get re-rendered when data arrives.
2. `eventDidMount` calls `info.el.remove()` — removing FC's DOM nodes causes FC to re-create them on navigation/re-render, which is why pills keep reappearing.
3. The CSS `!important` hide rules are a brittle band-aid that FC's virtual DOM updates bypass.

**Root cause:** The approach of rendering events then hiding them is fundamentally wrong. Events should never render at all.

---

## Solution: Eliminate Event Rendering Entirely

### Core Strategy

Use FullCalendar's `events` as a **function** (not eventSources) to:
1. Fetch events manually via `fetch()`
2. Build `dateStatusMap` AND `dateUrlMap` from the response
3. Return **empty array** to FC so zero event elements are ever created

This eliminates ALL pill/dot/more-link issues permanently because FC never has events to render.

### Why This Works in FC 6.1.10

FullCalendar's `events` option accepts a function with signature `(fetchInfo, successCallback, failureCallback)`. When the function calls `successCallback([])`, FC renders a calendar with no events. The `dayCellDidMount` callback still fires for every cell, giving us full control over coloring.

---

## File Changes

### 1. `static/js/main.js` — Rewrite `initCalendar()`

**Lines ~6–79** (the entire function body)

#### a) Replace `eventSources` with `events` function

```javascript
events: function(fetchInfo, successCallback, failureCallback) {
    fetch(eventsUrl + '?start=' + fetchInfo.startStr + '&end=' + fetchInfo.endStr)
        .then(r => r.json())
        .then(events => {
            // Clear maps
            Object.keys(dateStatusMap).forEach(k => delete dateStatusMap[k]);
            Object.keys(dateUrlMap).forEach(k => delete dateUrlMap[k]);

            events.forEach(function(ev) {
                if (ev.start && ev.extendedProps && ev.extendedProps.status) {
                    dateStatusMap[ev.start] = ev.extendedProps.status;
                    dateUrlMap[ev.start] = ev.url;
                }
            });

            // Return empty array — no event elements rendered
            successCallback([]);
        })
        .catch(err => {
            console.error('Calendar fetch failed:', err);
            failureCallback(err);
        });
},
```

#### b) Add `dateUrlMap` alongside `dateStatusMap`

```javascript
const dateStatusMap = {};
const dateUrlMap = {};
```

#### c) Remove `eventContent`, `eventDidMount`, and `eventClick`

These callbacks become dead code since no events are rendered. Remove them entirely.

#### d) Update `dayCellDidMount` — solid colors + pointer cursor + click navigation

```javascript
dayCellDidMount: function(info) {
    // Remove "+more" link (safety net — shouldn't appear without events)
    const moreLink = info.el.querySelector('.fc-daygrid-more-link');
    if (moreLink) moreLink.remove();

    const dateStr = info.date.toISOString().slice(0, 10);
    const status = dateStatusMap[dateStr];

    if (status) {
        info.el.style.cursor = 'pointer';

        if (status === 'confirmé' || status === 'terminé') {
            info.el.style.backgroundColor = '#06d6a0';
            info.el.style.color = '#ffffff';
        } else if (status === 'en attente') {
            info.el.style.backgroundColor = '#ffd166';
            info.el.style.color = '#333333';
        } else if (status === 'changé de date') {
            info.el.style.backgroundColor = '#118ab2';
            info.el.style.color = '#ffffff';
        } else if (status === 'annulé') {
            info.el.style.backgroundColor = '#ef476f';
            info.el.style.color = '#ffffff';
        }

        // Make the day number text inherit the color
        const dayNumber = info.el.querySelector('.fc-daygrid-day-number');
        if (dayNumber) dayNumber.style.color = info.el.style.color;
    }
},
```

#### e) Update `dateClick` — navigate to event detail when booking exists

```javascript
dateClick: function(info) {
    const url = dateUrlMap[info.dateStr];
    if (url) {
        window.location.href = url;
    } else {
        window.location.href = '/evenement/nouveau?date=' + info.dateStr;
    }
},
```

#### f) Keep existing options unchanged

- `initialView: 'dayGridMonth'`
- `locale: 'fr'`
- `headerToolbar` (prev, next, today, title, dayGridMonth, listMonth)
- `height: 'auto'`
- `dayMaxEvents: false`
- `navLinks: true`
- `nowIndicator: true`

---

### 2. `app/templates/bookings/calendar.html` — Simplify CSS

**Lines ~43–57** (the inline `<style>` block)

Replace the aggressive event-hiding CSS with minimal rules since no events will render:

```html
<style>
/* Day cell base styling */
.fc-daygrid-day { cursor: default; }
.fc-daygrid-day:hover { filter: brightness(1.08); }

/* Safety net: hide any residual event elements */
.fc-daygrid-day-events,
.fc-daygrid-event-harness,
.fc-daygrid-event,
.fc-h-event,
.fc-event,
.fc-daygrid-more-link {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}
</style>
```

Keep the safety-net CSS as a belt-and-suspenders approach, but it should never activate.

---

### 3. No API Changes

The `/api/calendar-events` endpoint already:
- Accepts `start`/`end` query params (used by FC's fetchInfo)
- Returns `url` field per event (used by dateUrlMap)
- Returns `extendedProps.status` (used by dateStatusMap)
- Returns `backgroundColor`/`borderColor` (unused but harmless)

No changes needed.

---

## Why Previous Attempts Failed

| Attempt | Why It Failed |
|---|---|
| `eventContent: () => ({ html: '' })` | FC 6 still creates wrapper elements around empty content |
| `eventDidMount: (info) => info.el.remove()` | FC re-creates removed elements on re-render (month nav, filter) |
| CSS `display: none !important` | FC applies inline styles and re-creates elements dynamically |
| `dayCellDidMount` coloring with `eventSources` | Race condition: map is empty when cells first render |

**This plan eliminates the root cause**: FC never receives events, so it never creates event DOM nodes.

---

## Test Impact

All 5 tests in `TestCalendar` pass without changes:

| Test | Why It Still Passes |
|---|---|
| `test_calendar_loads` | GET `/calendrier` still returns 200 (template unchanged structurally) |
| `test_calendar_shows_fullcalendar` | `<div id="fullcalendar">` still present (no template structure change) |
| `test_calendar_with_venue_filter` | Venue filter is server-side, calendar.html still renders the form |
| `test_calendar_api_returns_events` | API endpoint unchanged — still returns JSON with colors and status |
| `test_calendar_api_fullcalendar_start_end` | API still accepts start/end params — now FC actually sends them via our fetch |

**New behavior verified by tests:**
- API receives proper `start`/`end` params from FC's fetchInfo (previously eventSources sent them automatically; our manual fetch does the same)
- Response structure unchanged (tests check `backgroundColor`, `borderColor`, `extendedProps.status`)

---

## Verification Steps

After implementation:

1. `python3 -m pytest tests/test_bookings.py -k calendar -v` — all 5 tests pass
2. Manual: Open `/calendrier` — day cells with bookings are solid green/yellow blocks
3. Manual: No event pills, titles, dots, or "+more" links visible
4. Manual: Click a colored day → navigates to event detail page
5. Manual: Click an empty day → navigates to create new event page
6. Manual: Month navigation (prev/next) preserves coloring
7. Manual: Venue filter dropdown reloads calendar with correct coloring
8. Manual: Legend sidebar still visible and correct

---

## Rollback

If anything breaks, revert `static/js/main.js` and `app/templates/bookings/calendar.html` to previous state. No API or model changes, so no migration rollback needed.
