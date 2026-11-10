"""夜审修复 r5：幂等唯一窗口＋单点现行唯一＋run_id FK 索引（CR-045/048/053/059）。

拍板 2026-11-10（蔡工授权迁移窗口一次做，留痕可推翻）——四个审查发现合并
一个 additive 迁移窗口：

- ``uq_agent_runs_idempotency_active``（CR-045）：部分唯一索引——同一幂等键
  的 in-flight run（queued/running/host_running）至多一行。并发同键 start 的
  败者撞索引 ⇒ 服务层兜底重读返回既有 run（双执行双计费结构不可能）。
  终态行不进谓词——重试链（retry 与原 run 共享幂等键）零影响。
- ``uq_agent_artifacts_run_storage_ref``（CR-048）：产物（run_id, storage_ref）
  唯一——宿主回执并发窗口重复产物行结构不可能；前导列 run_id 同时补上
  CR-059 的产物详情页 FK 查询（独立 ix 冗余故不另建）。
- ``uq_delivery_plans_project_published``（CR-053，复核员校正口径）：单项目
  现行发布方案至多一份——并发双点永久共存封死（时序正确性仍由 publish 的
  supersede-先行保证，索引只兜并发窗口）。
- ``uq_test_plans_project_approved``（CR-053）：单项目现行批准测试计划至多
  一份（同上）。
- ``ix_agent_tool_calls_run``（CR-059）：agent_tool_calls.run_id FK 索引
  （详情页必经查询；活库现测 2026-11-10 仅 pkey）。

**零数据手术**：活库现测（2026-11-10，先测后建）四个唯一面全部零重复
（in-flight run 0 行／artifacts 46 行无 (run,ref) 重复／published 1 行／
approved 1 行）——纯 additive 建索引；未来存量若脏，CREATE UNIQUE INDEX
大声失败（升级前人工清），迁移不做静默去重。

Backup hint: additive only; downgrade drops the five indexes.
"""
import sqlalchemy as sa
from alembic import op

revision = "a9c5e2d7b3f1"
down_revision = "a5e9c3f1b7d4"  # 十五/十六度插队连改挂：现 M1 a5e9c3f1b7d4 之后，保单头
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_agent_runs_idempotency_active",
        "agent_runs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'host_running')"),
    )
    op.create_index(
        "uq_agent_artifacts_run_storage_ref",
        "agent_artifacts",
        ["run_id", "storage_ref"],
        unique=True,
    )
    op.create_index(
        "uq_delivery_plans_project_published",
        "delivery_plans",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index(
        "uq_test_plans_project_approved",
        "test_plans",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )
    op.create_index("ix_agent_tool_calls_run", "agent_tool_calls", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_tool_calls_run", table_name="agent_tool_calls")
    op.drop_index("uq_test_plans_project_approved", table_name="test_plans")
    op.drop_index("uq_delivery_plans_project_published", table_name="delivery_plans")
    op.drop_index("uq_agent_artifacts_run_storage_ref", table_name="agent_artifacts")
    op.drop_index("uq_agent_runs_idempotency_active", table_name="agent_runs")
