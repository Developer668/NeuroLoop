"""Forward-only, transactional SQLite migrations; refuses unknown future schemas."""
from sqlalchemy import text

MIGRATIONS = {
    2: ["""CREATE TABLE IF NOT EXISTS external_receipts (
        id VARCHAR(36) PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt FLOAT NOT NULL DEFAULT 0, external_id TEXT, url TEXT,
        error TEXT, created_at TEXT NOT NULL, delivered_at TEXT)""",
        "CREATE INDEX IF NOT EXISTS ix_external_pending ON external_receipts(status, next_attempt)"],
    3: ["""CREATE TABLE IF NOT EXISTS agent_proposals (
        id VARCHAR(36) PRIMARY KEY, version INTEGER NOT NULL, source TEXT NOT NULL,
        specification TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed',
        run_id TEXT, created_at TEXT NOT NULL)"""],
}

def upgrade(engine):
    from .db import now
    with engine.begin() as connection:
        current = connection.execute(text('SELECT COALESCE(MAX(version),0) FROM schema_version')).scalar_one()
        if current > max(MIGRATIONS):
            raise RuntimeError('Database belongs to a newer NeuroLoop release; upgrade the application.')
        for version, statements in MIGRATIONS.items():
            if version <= current:
                continue
            for statement in statements:
                connection.execute(text(statement))
            connection.execute(text('INSERT INTO schema_version(version,installed_at) VALUES (:v,:t)'), {'v':version,'t':now()})
