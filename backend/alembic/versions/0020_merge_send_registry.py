"""Join shared-send audit and workspace registry migration histories.

Both parents own durable data. This revision only reconciles the graph so the
normal ``upgrade head`` path applies both prerequisites without deleting either.
"""

revision = "0020_merge_send_registry"
down_revision = ("0018_security_audit_events", "0019_email_read_state_repair")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Join already-applied parent revisions without changing their data."""


def downgrade() -> None:
    """Split revision bookkeeping without deleting parent-owned data."""
