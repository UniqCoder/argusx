"""
app/models/__init__.py — Import all ORM models here.

Alembic's env.py imports this module so that Base.metadata contains all
table definitions when generating migrations.
"""
from app.models.complaint import Complaint, ComplaintWallet  # noqa: F401
from app.models.wallet import Wallet  # noqa: F401
from app.models.case import Case, CaseWallet  # noqa: F401
from app.models.alert import Alert  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
