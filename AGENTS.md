# Samba Fête — Agent Instructions

## Project
Flask booking/event management app for a DJ/entertainment company.
Deployed on Railway at https://web-production-089fe.up.railway.app

## Tech Stack
- Python 3 + Flask
- SQLAlchemy ORM + SQLite
- Bootstrap 5 dark theme (midnight blue + gold)
- Pure HTML/CSS/JS calendars (no FullCalendar)
- Railway deployment, GitHub auto-deploy

## Rules
- Always use OpenCode for coding tasks
- Test with `python3 -m py_compile` before committing
- All POST forms need CSRF tokens (`{{ csrf_token() }}`)
- All routes need `@login_required`
- Push to origin main after changes
- Login: admin / Ramsys2020$

## Key Files
- `app/bookings/routes.py` — main booking routes
- `app/clients/routes.py` — client routes
- `app/finance/routes.py` — finance/export routes
- `app/auth/routes.py` — authentication
- `app/templates/bookings/` — booking templates
- `static/css/style.css` — all styles
- `static/js/main.js` — JavaScript utilities

## Smart Skill Usage

### When to plan before coding
Use the **planner** agent BEFORE any of these:
- Adding a new page or module
- Changing database schema
- Modifying the booking flow
- Adding new API endpoints
- Any change affecting multiple files

### When to use TDD
Use **tdd-guide** when:
- Adding new form validation
- Creating new routes
- Modifying payment calculations
- Changing date/status logic

### When to review code
Use **code-reviewer** after:
- Any route changes
- Template modifications
- Security-sensitive code (auth, payments)
- Before pushing to production

### When to use security review
Use **security-reviewer** when:
- Adding new forms or inputs
- Modifying authentication
- Changing payment handling
- Adding file uploads
- Modifying CSRF or session logic

### Quick patterns
- **New page** → Plan → Code → Review → Push
- **Bug fix** → Read code → Fix → Test → Push
- **UI change** → Screenshot issue → Fix CSS → Push
- **Database change** → Plan → Migration → Test → Push

## Database
- SQLite at `instance/samba_fete.db`
- Key tables: events, clients, payments, venues, expenses
- event_date is TEXT (YYYY-MM-DD format)
- Status values: "confirmé", "en attente", "terminé", "changé de date", "annulé"

## Deployment
- Push to GitHub → Railway auto-deploys
- Railway URL: https://web-production-089fe.up.railway.app
- No manual deployment needed
