"""gate template hash audit column

Adds gates.template_hash (sha256 of seeds/gates.json at instantiation time) so
frozen checklists on existing projects are auditable against template drift.
Backfills existing rows with the current file hash (they were all instantiated
from this version).
"""
from alembic import op
import sqlalchemy as sa

revision = "f7a2c9e4b1d3"
down_revision = "c9f2d4e8a1b7"
branch_labels = None
depends_on = None

GATES_JSON_SHA256 = "f52afe884af8026eef28af66abdae0d2c8f7b07a25d100bf0a647276b51647e6"


def upgrade() -> None:
    op.add_column("gates", sa.Column("template_hash", sa.String(64), nullable=True))
    op.execute(
        "UPDATE gates SET template_hash = '" + GATES_JSON_SHA256 + "' WHERE template_hash IS NULL"
    )


def downgrade() -> None:
    op.drop_column("gates", "template_hash")
