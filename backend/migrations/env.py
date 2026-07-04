"""Alembic environment — sources the DB URL and metadata from the app itself
so migrations never drift from the settings/model definitions used at runtime.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base
from app.core.security import EncryptedString

# Import models so Base.metadata is fully populated before autogenerate runs.
from app.models import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """Render custom TypeDecorator columns (EncryptedString) as their
    underlying physical type (Text) in generated migrations.

    Without this, autogenerate emits a literal ``app.core.security.
    EncryptedString()`` reference with no import statement, which raises
    ``NameError`` the moment the migration runs. The DB schema only needs to
    know the physical column type — encryption/decryption happens in Python
    via process_bind_param/process_result_value, not in DDL.
    """
    if type_ == "type" and isinstance(obj, EncryptedString):
        return "sa.Text()"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
