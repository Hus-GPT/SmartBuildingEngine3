# SmartBuildingEngine

Telegram-first personal building management system.

## Architecture

- `app/domain`: business entities and rules
- `app/application`: Telegram-independent use cases
- `app/infrastructure`: SQLAlchemy persistence, file storage, PDF rendering, audit records
- `app/interfaces/telegram`: Telegram adapter only
- `tests`: automated business-rule and persistence tests

The business/application layers do not depend on Telegram.

## Current scope

- Single building / single owner
- Apartments and shops
- Tenants with multiple phones and historical leases
- One active lease per unit
- Electricity and water meters with non-decreasing readings
- Monthly combined utility/shared-expense invoices
- Partial payments
- File/image storage
- Immutable archived invoices
- Explicit confirmation for sensitive writes
- Audit log
- PDF invoice rendering

## Safety principle

No destructive or financially significant write is executed silently. The system validates the operation, requires explicit confirmation, then records the operation in the audit log.

## Development status

The project is being rebuilt from a clean foundation. The persistence schema, core transactional use cases, owner-only Telegram boundary, file storage, PDF renderer, and initial tests are now in place. Telegram workflows and full invoice lifecycle are next.

## Run

1. Install dependencies: `pip install -e .[test]`
2. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_ID`.
3. Run: `python -m app.main`
4. Test: `pytest`
