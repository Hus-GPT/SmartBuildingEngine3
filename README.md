# SmartBuildingEngine

Telegram-first personal building management system.

## Architecture

- `app/domain`: business entities and rules
- `app/application`: use cases and orchestration
- `app/infrastructure`: persistence, files, PDF generation, audit
- `app/interfaces/telegram`: Telegram adapter only
- `tests`: automated business-rule tests

The business/application layers do not depend on Telegram.

## First release scope

- Single building
- Apartments and shops
- Tenants and historical leases
- Electricity and water meters
- Monthly combined utility/shared-expense invoices
- Partial payments
- File/image storage
- Immutable approved/archived invoices
- Explicit confirmation for sensitive writes
- Audit log
- Arabic invoice output as PDF

## Safety principle

No destructive or financially significant write is executed silently. The system validates the operation, presents a clear warning, requires explicit confirmation, then records the operation in the audit log.
