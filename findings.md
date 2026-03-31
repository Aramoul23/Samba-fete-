# Findings: Samba Fête Calendar Enhancement

## Current Architecture
- **Calendar route:** `/calendrier` → `calendar_view()` (in `app/bookings/routes.py`)
- **Event form route:** `/evenement/nouveau` → supports `?date=YYYY-MM-DD` query param (already works)
- **Event detail route:** `/evenement/<id>` → shows full event info
- **Template:** `templates/calendar.html` — FullCalendar-style grid with JavaScript click handlers

## Current Click Flow (to be replaced)
```
User clicks date
  → showDayDetail(dateStr, hasEvents, status)
    → if free: shows modal "Available" + "Add Event" button → redirects to /evenement/nouveau?date=X
    → if booked: shows bookedErrorModal with event list + "Voir Détails" links
    → if pending: shows pendingModal with event list + "Voir Détails" links
```

## Target Click Flow
```
User clicks date
  → if free: window.location = /evenement/nouveau?date=YYYY-MM-DD
  → if booked/pending: window.location = /evenement/<event_id>
```

## Multi-Event Edge Case
When a date has multiple events, we need to decide: redirect to first event, or show a picker?
- Current code iterates `day_events` and shows up to 3 dots
- Need to handle this in the new click handler

## Routes Confirmed
- `/evenement/nouveau?date=YYYY-MM-DD` — already exists, date pre-fills via `request.args.get('date', '')`
- `/evenement/<int:event_id>` — already exists for event detail
- Event IDs are available in `booked_dict` JSON passed to template
