# R1c 固定产物与隔离恢复验收规格

首轮覆盖 `api`、`worker`、`scheduler`、PostgreSQL 和本地文件存储。R1c-1 校验合成数据包的清单及字节，R1c-2 使用同一产物包在专用环境执行恢复。生产操作命令以 [README](../../README.md) 为准。

## 承重假设与停止条件

| 假设 | 最小反证 | 停止条件 |
|---|---|---|
| 批准的清单来自独立发布记录 | 同时替换附件和清单，再使用原批准指纹核验 | 清单指纹不一致即拒绝 |
| 清单对应实际运行的镜像和迁移 | 恢复后逐项对照实际镜像 ID、迁移包、挂载来源及库中头 | 任意一项不一致即判失败 |
| 数据库和附件来自同一业务截止点 | 用合成项目记录与附件组成关联样本，在写入冻结后采集，恢复后逐项核对 | 缺冻结窗口回执或记录、附件、密文任一不符即判失败 |
| 演练目标与生产隔离 | 在读入备份之前核对专用 PG、卷、网络、目标容器标识和外连限制 | 存在共享 DB/卷、对外发信、桥或模型通道即停止 |

## R1c-1 清单校验

- 允许修改 `scripts/deploy/recovery_manifest.py`、对应 `tests/deploy/` 测试、`docs/optimization/` 和本轮 CHANGELOG。
- `verify --bundle <目录> --expected-manifest-sha256 <64 位小写十六进制>` 接受已封存的演练目录。路径为空或含 `..` 分量时返回 `invalid_bundle_path`。由独立批准记录提供清单 SHA-256。执行者固定好目录，直到校验与恢复结束。
- `manifest.json` 为 UTF-8 JSON 对象，最大 64 KiB，禁止重复键和未知字段。v1 固定字段为 `schema_version`（整数 1）、`commit`（40 位小写十六进制）、`release_input_fingerprint`（把 R1a 输出的 `input_sha256` 以键排序、去空白、ASCII 转义的紧凑 JSON 转为 UTF-8 后计算 SHA-256）、`migration_head`（1–32 位 ASCII 字母、数字、下划线）、`capture_id`（32 位小写十六进制）和 `artifacts`。
- `artifacts` 为按角色索引的对象。每项含 `size_bytes`（正整数）及 `sha256`（64 位小写十六进制）；镜像项另含 `image_id`（`sha256:` 加摘要）及 `platform`（`linux/amd64` 或 `linux/arm64`）。角色及实际文件名为下表。

| 角色 | 文件名 |
|---|---|
| `api` | `api-image.tar` |
| `worker` | `worker-image.tar` |
| `scheduler` | `scheduler-image.tar` |
| `migrations` | `migrations.tar` |
| `postgres` | `postgres.dump` |
| `storage` | `storage.tar` |

- 核验器只读取预定普通文件，流式复算 SHA-256 并核长度。固定文件名避免清单携带路径；拒绝符号链接、重解析点和多硬链接。错误输出固定代码与角色。`bundle_verified` 仅表示本次读取的清单与产物字节匹配，输出 `restore_status=not_checked`。校验过程拥有对封存目录的普通读取权限。快照保护由演练执行侧提供。

## R1c-2 恢复演练验收

使用专用项目和隔离网络，独立 PostgreSQL、Redis、卷和端口。采用仅供演练的根密钥。采集与恢复均使用合成数据。验收记录应包含冻结窗口、对象数与关键字段、附件逐位 SHA-256、密文经应用读面解密的通过状态、实际镜像 ID、挂载源、库中 head 与 readiness。密钥仅保留在演练进程配置内，报告记录通过或失败。

对错误镜像或迁移包、缺备份、附件损坏、错误密钥、目标未隔离分别保留拒绝回执。分别登记准备、恢复、验证耗时及合成写入水位差。RTO/RPO 达标取决于另行批准的阈值。

演练脚本与目标清单在执行前复核，包含具体工作目录、项目名、卷、端口、网络、测试库和结束方式。其执行证据独立于清单校验回执。

### R1c-2a 离线编排

写入范围包括 `scripts/deploy/recovery_rehearsal.py`、清单校验器的函数返回契约、对应的部署工具测试和本轮文档。

`execute_rehearsal(plan, steps)` 接收演练资源计划和可信的调用方回调。计划包含批准清单指纹、采集批次、提交、迁移头、镜像 ID、资源名和路径、连接地址、密钥指纹以及附件和解密样本的预期值。演练路径位于专用根内且互不重叠，已存在的各级路径须为普通目录。项目、网络和卷名与采集批次绑定。三个端点使用 `127.0.0.1` 及互异的 `20000–29999` 端口。PG 使用批次专用数据库，Redis 使用 `/9`，readiness 使用 `/api/v1/health/ready`。

计划及回调集合通过检查后，复用 R1c-1 校验器读取清单和文件，再把计划中的批次、提交、迁移头及镜像 ID 与清单逐项比对。通过后依次执行 `preflight → restore_database → restore_storage → apply_migrations → verify_crypto → verify_images → verify_mounts → probe_readiness`。阶段核验覆盖目标隔离声明、数据库批次及水位证据、附件数量及摘要、迁移头、解密样本、镜像 ID、挂载隔离和 readiness `200/ok`。证据不符或回调失败时立即停止。

版本 1 报告包含 `capture_id`、`bundle_verified`、`status`、`restore_status`、各已尝试回调的 `timings_ms` 以及已通过的证据摘要。执行前拒绝使用 `rejected/not_run`，阶段失败使用 `restore_failed/blocked`，全部证据匹配使用 `restore_verified/passed`。错误仅含固定代码与阶段或字段名。报告按允许字段生成快照，路径、连接串、密钥指纹、解密样本指纹和异常原文留在报告之外。

### R1c-2a 冻结水位核对

构造 `RehearsalPlan` 时必传正整数 `expected_watermark`，取自数据库停止写入后、采集备份前登记的合成写入水位。恢复回调在恢复库中读取同一种水位。批次、对象数和水位均须匹配。水位不符在 `restore_database` 阶段返回 `database_evidence_mismatch` 并停止。计划水位无效时在调用回调前拒绝。v1 成功报告的 `evidence.database.watermark` 记录实读值。

回退可撤销本轮补丁，并将调用方恢复为上一版 `RehearsalPlan` 参数。冻结回执、恢复库实读及 RTO/RPO 的测量归 R1c-2b。

### R1c-2b 实机取证

接入隔离环境适配器并执行本节上方的恢复验收。适配器负责在整个运行窗口固定产物和目标、验证实际资源归属、关闭外部通道、核对对象及写入水位差，并回收演练资源。R1c-2a 的验证采用合成回调和本地文件。实机隔离、冻结窗口、数据恢复及准备、恢复和核验耗时在 R1c-2b 记录。
