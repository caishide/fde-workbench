"""goal-d1 (S0-1): presurvey_intakes — 售前轻量录入卡

PRD F1 / 决议 D16（交付工作台升级，2026-10-31 party mode 定稿）：
- 每项目一张轻量录入卡（1:1，PK=project_id）：行业/规模/地域/访谈方式/
  对象角色/诉求一句话/阶段目标/备注——全部无敏感字段，S1–S2 即可填写，
  数据口径等价 SOP leads.md 九字段，不触碰「售前资料 S3 前禁入库」红线。
- DOCX 上传与 AI 分析链路的 G3 前置闸是 service 层校验（无 schema 变更）。

Backup hint: pure CREATE TABLE, no data written.
Downgrade drops the table.
"""
from alembic import op
import sqlalchemy as sa


revision = "a7f3c1e9d5b2"
down_revision = "f4b8c2d6e3a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "presurvey_intakes",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("industry", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("scale", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("region", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("interview_mode", sa.String(length=16), nullable=False, server_default="onsite"),
        sa.Column("interviewee_roles", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("customer_vision", sa.Text(), nullable=False),
        sa.Column("phase_objective", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "interview_mode IN ('onsite', 'remote', 'hybrid')",
            name="ck_presurvey_intakes_interview_mode",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_presurvey_intakes_project", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], name="fk_presurvey_intakes_updater", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("project_id", name="pk_presurvey_intakes"),
    )


def downgrade() -> None:
    op.drop_table("presurvey_intakes")
