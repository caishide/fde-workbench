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
