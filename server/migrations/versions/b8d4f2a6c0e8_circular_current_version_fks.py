"""add circular current-version foreign keys

The baseline create_table silently skipped the three use_alter=True circular
foreign keys, so the models declared referential integrity the database never
enforced (alembic check flags them as add_fk). This revision adds them:
project_files/project_documents current_version_id pointers and the
project_research_forms current-revision receipt constraint.

Backup hint: ALTER TABLE ADD CONSTRAINT only, no data written. If a business
database holds dangling current_version_id / current_revision_id pointers the
upgrade fails loudly; clean those rows first, no automatic rewrite happens.
"""
from alembic import op

revision = "b8d4f2a6c0e8"
down_revision = "f7a2c9e4b1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_project_files_current_version_id",
        "project_files",
        "project_file_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_project_documents_current_version_id",
        "project_documents",
        "project_document_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_project_research_forms_current_revision_id",
        "project_research_forms",
        "project_research_form_revisions",
        ["id", "current_revision_id"],
        ["form_id", "id"],
        ondelete="RESTRICT",
        use_alter=True,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_project_research_forms_current_revision_id",
        "project_research_forms",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_project_documents_current_version_id",
        "project_documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_project_files_current_version_id",
        "project_files",
        type_="foreignkey",
    )
