# Task Plan: Samba Fête Calendar Click-to-Create/View + One-Event-Per-Day Rule

## Goal
1. Calendar click: free date → event creation form (date pre-filled). Taken date → event detail page. No modals.
2. Enforce one event per day across ALL venues (big hall, jardin, etc.). Block creation if date already has an event.

## Current Phase
Phase 1 — Requirements confirmed, planning complete.

## Phases

### Phase 1: Requirements & Codebase Analysis
- [x] Read calendar.html template
- [x] Read event_form.html template  
- [x] Identify current click handler (`showDayDetail`)
- [x] Identify routing structure (bookings/routes.py)
- [x] Clarify behavior with user
- **Status:** complete

### Phase 2: Modify Calendar Click Behavior
- [ ] **Free date click** → Redirect directly to `/evenement/nouveau?date=YYYY-MM-DD`
- [ ] **Taken date (confirmé or en attente)** → Redirect directly to `/evenement/<id>` (event detail page)
- [ ] Remove intermediate modals (`dayDetailModal`, `bookedErrorModal`, `pendingModal`)
- [ ] Keep existing visual styling (colors, dots, legends) intact
- **Status:** pending

### Phase 3: Enforce One-Event-Per-Day Rule (Backend)
- [ ] Add validation in booking creation route: reject if date already has any event (any venue, any status)
- [ ] Add validation in booking update route: reject date change if target date already occupied
- [ ] Return clear French error message: "Cette date est déjà réservée"
- [ ] Disable the date in Flatpickr date picker (event_form.html) if date is taken
- **Status:** pending

### Phase 4: Testing & Verification
- [ ] Test free date click → lands on event form with date pre-filled
- [ ] Test taken date click → lands on event detail page
- [ ] Test creating event on occupied date → blocked with error message
- [ ] Verify no broken links or JS errors
- **Status:** pending

## Key Questions
1. ~~Should clicking a date with MULTIPLE events show a list to pick from, or go to the first event?~~
   → **RESOLVED: Not applicable — one event per day enforced.**

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Direct redirect instead of modal | User explicitly requested "comes directly" — no intermediate step |
| Keep visual calendar styling | Works well, no reason to change colors/legends |
| Both booked AND pending → event detail | User said "if it's taken goes to show more information" — covers both statuses |
| One event per day (all venues) | User requirement — simplifies calendar, prevents double-booking across venues |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| — | — | — |
