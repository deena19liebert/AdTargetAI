# app/db/base.py
from sqlalchemy.orm import declarative_base

# single source of truth for Alembic autogenerate
Base = declarative_base()

# Import models to register them with Base.metadata.
# Importing here is fine — models import Base (no circular import issues).
# Keep this list in sync whenever you add models.
from app.db.models import (
    campaign,
    platform_feed,
    facebook_details,
    export_log,
    uploaded_image,
    user,  # NEW
    transaction,  # NEW
    credit_usage  # NEW
)





