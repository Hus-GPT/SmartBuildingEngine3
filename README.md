# SmartBuildingEngine

Telegram-first personal building management system.

## Architecture

- `app/domain`: business entities and rules
- `app/application`: Telegram-independent use cases
- `app/infrastructure`: SQLAlchemy persistence, file storage, PDF rendering, backup, audit records
- `app/interfaces/telegram`: Telegram adapter and interactive workflows
- `tests`: automated business-rule, persistence, lifecycle, backup, and import tests

The business/application layers do not depend on Telegram.

## Current scope

- Single building / single owner
- Apartments and shops
- Tenants with multiple phones and preserved historical records
- One active lease per unit
- Complete lease wizard: unit + tenant + dates + rent/deposit + two witnesses + contract + guarantee + final confirmation
- Contract end / early move-out with audit trail
- Contract renewal as a new lease beginning after the previous lease ends
- Automatic lease duration calculations
- Expiring-contract query, default 15-day window
- Electricity and water meters with non-decreasing readings
- Monthly combined utility/shared-expense invoices
- Duplicate billing-period protection per unit
- Partial payments and outstanding-balance validation
- Arabic invoice PDF rendering with Arabic shaping/bidi support
- File/image storage
- Immutable issued/paid/archived invoice records
- Explicit confirmation for sensitive writes
- Audit log
- Building summary and unit occupancy/outstanding-balance status
- SQLite database + stored-file backup, retaining the latest backup

## Telegram commands

- `/start`, `/menu`
- `/units`, `/tenants`
- `/addunit`, `/addtenant`
- `/newlease` for the integrated complete-contract workflow
- `/endlease`, `/renewlease`, `/expiring`
- `/meter`
- `/invoice`, `/pay`
- `/doc`, `/witness`
- `/status`
- `/backup`

## Safety principle

No destructive or financially significant write is executed silently. The system validates the operation, presents a review/warning, requires explicit confirmation, then commits the transaction and records an audit entry.

## Development status

The clean rebuild has the core persistence layer, Telegram boundary, complete lease workflow, contract lifecycle, utility invoices/payments, Arabic PDF output, building reporting, backup, audit logging, and automated tests connected. GitHub Actions is used as the verification gate; the latest completed test workflow for the current development line passed.

The remaining work is deployment/operational hardening and real Telegram acceptance testing with the user's production environment and secrets. No production secret is stored in the repository.

## Run

1. Install dependencies: `pip install -e .[test]`
2. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_ID`.
3. Run: `python -m app.main`
4. Test: `pytest`
