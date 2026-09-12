from alembic import context
from sqlalchemy import engine_from_config, pool
from neuroloop_app.config import Settings
from neuroloop_app.db import Base
config=context.config
settings=Settings()
url=config.attributes.get("database_url") or settings.db_url
config.set_main_option("sqlalchemy.url", url.replace("%","%%"))
target_metadata=Base.metadata
if context.is_offline_mode():
    context.configure(url=url,target_metadata=target_metadata,literal_binds=True,dialect_opts={"paramstyle":"named"})
    with context.begin_transaction(): context.run_migrations()
else:
    engine=engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction(): context.run_migrations()
