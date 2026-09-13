"""Add is_read to emails (IMAP \\Seen read state).

Existing rows default to read so historical/file imports do not surface as unread.

Deliberate exception to this repo's "Alembic migrations use structured
operations (``op.create_index``, ...), never raw DDL" rule
(``AGENTS.md``/``CLAUDE.md``): ``upgrade()``/``downgrade()`` below use
``op.execute()`` with fixed module-level SQL constants instead of a structured
``op.*`` call. The reason a structured call isn't used is that this migration's
behavior must be conditional on whether the legacy ``emails`` table exists,
evaluated at apply time (see the comment on ``_UPGRADE_SQL`` below for why that
check cannot live in Python), and no structured Alembic operation expresses
"run this DDL only if a runtime condition holds". The SQL is entirely static:
no identifier or value is assembled from external input or runtime state.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_email_read_state"
down_revision = "0009_project_graph_projection"
branch_labels = None
depends_on = None

# Fresh installations materialize the current ``email_records`` model in the
# 0001 baseline, including ``is_read``. This historical side branch only
# applies to databases that still carry its legacy ``emails`` table.
#
# The condition has to be evaluated in SQL, not Python: offline SQL
# generation (``alembic upgrade --sql``, a real flag ``scripts/migrate_db.py``
# exposes) has no live connection to introspect with and no specific target
# database to ask "does this legacy table exist" at generation time either --
# the same static script is meant to later be applied by a DBA against
# whichever database they choose, fresh-install or legacy. A Python-side
# check (``sa.inspect(op.get_bind())``) can only ever answer that question
# for one hypothetical target chosen at generation time, so it is wrong for
# the other: skip unconditionally and the column silently never gets added
# for a legacy database that applies the generated script (while
# ``alembic_version`` still advances, permanently hiding the gap); inspect
# online and bake in one fixed answer and the same script fails outright
# against the other kind of target. A ``DO $$ ... $$`` block defers the
# check to apply time instead, so the one generated script is correct
# against either kind of target, online or offline-then-applied-later alike.
#
# ``to_regclass('emails')`` (not ``information_schema.tables`` by bare
# ``table_name``) deliberately: the unqualified ``ALTER TABLE emails`` below
# resolves through the connection's ``search_path``, and ``to_regclass``
# resolves an unqualified name exactly the same way, returning NULL if it
# doesn't. ``information_schema.tables`` filtered only by ``table_name``
# ignores ``search_path`` entirely and matches a same-named table in *any*
# schema the connecting role can see -- on a deployment with more than one
# accessible schema, that could find an unrelated ``emails`` table outside
# the search path while the unqualified ``ALTER TABLE emails`` targets a
# different (or no) table, passing the guard for the wrong relation or
# aborting the migration outright. Resolving both the check and the DDL
# through the same name lookup makes that mismatch structurally impossible.
#
# ``COMMENT ON COLUMN emails.is_read`` tags the column with a provenance
# marker (``_IS_READ_PROVENANCE_MARKER``) the moment upgrade() actually adds
# it. downgrade() only drops the column when that exact marker is present
# (CodeRabbit, naruon#1501): an ``emails.is_read`` column that already
# existed before this revision ran -- from some other, unrelated origin --
# would upgrade()'s ``NOT EXISTS`` guard correctly leave alone, but an
# unconditional ``DROP COLUMN IF EXISTS`` on downgrade would still destroy it
# and its data, since a downgrade has no other way to tell "I added this"
# apart from "this happens to be present". Checking the marker via
# ``col_description`` makes downgrade drop only what this exact revision's
# upgrade created. The regression test asserts this constant remains present
# in both static SQL blocks, preventing marker drift without constructing SQL.
_IS_READ_PROVENANCE_MARKER = "0011_email_read_state:added"
_UPGRADE_SQL = """
DO $$
BEGIN
    IF to_regclass('emails') IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = to_regclass('emails')
        AND attname = 'is_read'
        AND NOT attisdropped
    ) THEN
        ALTER TABLE emails ADD COLUMN is_read boolean NOT NULL DEFAULT true;
        COMMENT ON COLUMN emails.is_read IS '0011_email_read_state:added';
    END IF;
END $$;
"""

_DOWNGRADE_SQL = """
DO $$
BEGIN
    IF to_regclass('emails') IS NOT NULL AND EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = to_regclass('emails')
        AND attname = 'is_read'
        AND NOT attisdropped
    ) AND col_description(to_regclass('emails'), (
        SELECT attnum FROM pg_attribute
        WHERE attrelid = to_regclass('emails')
        AND attname = 'is_read'
        AND NOT attisdropped
    )) = '0011_email_read_state:added' THEN
        ALTER TABLE emails DROP COLUMN IF EXISTS is_read;
    END IF;
END $$;
"""


# This is fixed migration DDL, not application query construction. The raw-query
# Semgrep rule cannot distinguish this static Alembic boundary from runtime SQL.
def upgrade() -> None:
    op.execute(_UPGRADE_SQL)  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
