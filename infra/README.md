# Local development infrastructure

Phase 1 uses the existing local PostgreSQL installation and does not add containers or alter database contents. Set `DATABASE_URL` in `apps/api/.env` to a dedicated development database before starting the API. No migrations are included or run in this phase.
