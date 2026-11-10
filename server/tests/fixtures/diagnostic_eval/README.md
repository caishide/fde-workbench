# 诊断评测 fixtures（获客诊断工具 T-06）

> **这里放的是考卷，不是答案。** 标准答案（问题清单 / 方案方向 / 结果口径 / 人机边界）
> 只存本地真相层，仓库内**零答案内容**——生成器因此不可能从仓库读到答案。

## 目录内容

| 文件 | 说明 |
|---|---|
| `sync_from_truth_layer.py` | 从真相层案例卡生成 fixtures 的脚本（**按字段允许名单复制**） |
| `<case_id>.json` × N | 每张卡的**输入侧** fixtures：问卷槽位答案 + 自由文本痛点 + 刻意不完美说明 |
| `answer_key_digests.json` | 答案键**指纹登记表**：case_id → {相对路径, sha256} |

## 纪律

1. **答案键零内容**：fixtures 内不得出现任何答案字段（`ground_truth` /
   `solution_direction` / `problems_expected` / `human_boundary` /
   `must_not_hallucinate`）。由 `test_diagnostic_eval_contamination.py` 机械钉守。
2. **按允许名单复制**：同步脚本按字段允许名单取字段，**不在名单里的字段根本不会被读取**——
   禁止名单可被改名绕过，允许名单绕不过去。同步脚本源码内**不出现任何答案字段名**，
   因此它在结构上不可能复制答案。
3. **改答案必留 diff**：答案键改了 ⇒ sha256 变 ⇒ `answer_key_digests.json` 与
   fixtures 里的指针必须同步更新 ⇒ 仓库里看得见这次改动。评测曲线相应打**版本断点**，
   防止「改考题刷分」伪装成进化。
4. **禁止手改 fixtures**：一律由同步脚本重新生成（手改会在下一次同步时被覆盖，
   且与登记表不一致 ⇒ 机械钉转红）。
5. **展示面例外**：网站案例页与工具内示例报告**可以**消费答案生成展示内容，
   但那不在这份 fixtures 里，且须带「示例案例 · 据公开案例整理」/「脱敏真实交付 · 代号化」角标。

## 重新生成

```bash
# Windows 默认真相层
python server/tests/fixtures/diagnostic_eval/sync_from_truth_layer.py

# 显式指定真相层
FDE_DIAG_EVAL_TRUTH_ROOT=/path/to/诊断案例集 \
  python server/tests/fixtures/diagnostic_eval/sync_from_truth_layer.py
```

真相层不在场时脚本 **fail-closed**（退出码 2），不静默产出空 fixtures。

## 真相层在哪

`D:\test\FDE\knowledge\诊断案例集\`（本地真相层，**不入仓、不入远端**）。
仓库存的对应登记面是 `docs/audit/诊断评测-首批案例清单与指纹-2026-11-10.md`。
