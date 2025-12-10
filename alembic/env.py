# alembic/env.py
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "app")))

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.db.base import Base

# Import all models to ensure they're registered with Base.metadata
from app.db.models.campaign import Campaign
from app.db.models.platform_feed import PlatformFeed  
from app.db.models.facebook_details import FacebookDetails
from app.db.models.export_log import ExportLog
from app.db.models.uploaded_image import UploadedImage

target_metadata = Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()