-- Extensions (Alembic migrations run after this, but we enable extensions here
-- so they're available from the first connection)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
