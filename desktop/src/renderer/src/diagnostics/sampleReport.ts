import type { ReportDoc } from "./publicDiagnosticApi"

/**
 * 工具内**示例报告**（获客诊断 E-3 拍板顺序的前半：先工具内示例报告）。
 *
 * 纪律（任务书 R-6 / P-8）：
 *
 * 1. **必须带角标**——每则示例带「示例案例 · 据公开案例整理」或
 *    「脱敏真实交付 · 代号化」角标，页面同时声明「不是实时诊断结果」。
 * 2. **不得呈现为实时诊断结果**——示例正文用「示例」语气，页脚标注整理
 *    日期与「非实时生成」，不写「生成于」。
 * 3. **无分数无金额**（R-1 / R-4）——示例正文一律定性表述，不出现评分、
 *    百分比评级或补贴金额；政策条目的数字只来自**政策引文原文**。
 * 4. **展示产物不得被生成器检索路径引用**——本文件位于桌面端
 *    （``desktop/src``），生成器检索面在服务端（``server/src/fde_api/
 *    diagnostics`` ＋ ``server/seeds``），两者不相交。
 * 5. **素材只取展示面**——内容按公开案例整理并独立重写；内部交付件全部以
 *    代号指代，真实企业名与联系人信息不进入本仓。
 *
 * 结构与活体报告**同构**（``ReportDoc``），共用同一份渲染组件——示例与真实
 * 交付物不会各长各的。
 */

/** 示例角标（与任务书 R-6 固定文案一致）。 */
export const SAMPLE_BADGE_PUBLIC_CASE = "示例案例 · 据公开案例整理"
export const SAMPLE_BADGE_INTERNAL_DELIVERY = "脱敏真实交付 · 代号化"

/** 一则示例案例（报告本体 + 角标 + 溯源说明）。 */
export type SampleCase = {
  /** 案例标识（公开案例用其编号；内部交付件用代号）。 */
  caseId: string
  /** 角标文案（二选一，见上方常量）。 */
  badge: string
  /** 案例标题（页面上作为可选项）。 */
  title: string
  /** 一句话说明（行业与规模）。 */
  summary: string
  /** 溯源说明（来源与改写声明）。 */
  attribution: string
  /** 补充说明（如「本例未匹配到政策条目」）。 */
  note?: string
  /** 报告本体（与活体报告同构）。 */
  report: ReportDoc
}

/** 报告格式版本（与活体报告一致——示例同样按这个结构交付）。 */
const REPORT_FORMAT_VERSION = "diagnostic-report-v1"
/** 示例不是模型生成物——版本位显式标注为静态样例，不冒用提示词/数字闸版本。 */
const STATIC_SAMPLE_VERSION = "static-sample"
/** 政策口径快照日期（与服务端政策弹药库一致）。 */
const POLICY_SNAPSHOT_DATE = "2026-10-19"

const MANUFACTURING_SAMPLE: SampleCase = {
  caseId: "datawhale-001",
  badge: SAMPLE_BADGE_PUBLIC_CASE,
  title: "零部件制造 · 经验传承与新人上手",
  summary: "匿名德国零部件企业（制造业）／案例未披露具体人数",
  attribution:
    "示例案例 · 据公开案例整理｜来源：FDE-case-library（MIT License, © 2026 guminghao-avi contributors），原始出处 Datawhale《FDE案例100》NO.01｜本卡为独立重写",
  report: {
    version: REPORT_FORMAT_VERSION,
    prompt_version: STATIC_SAMPLE_VERSION,
    number_gate_version: STATIC_SAMPLE_VERSION,
    generated_at: "2026-11-12",
    layers: {
      situation: {
        headline: "老师傅一忙，新人就停在那儿：经验没有沉淀，上手速度取决于谁的班。",
        findings: [
          {
            id: "f1",
            stage: "identify",
            problem: "关键工艺与故障判断集中在资深员工个人经验里，没有沉淀成可检索的知识。",
          },
          {
            id: "f2",
            stage: "locate",
            problem: "新人依赖老师傅的可用性，响应速度与产能都受个人在不在岗牵制。",
          },
          {
            id: "f3",
            stage: "locate",
            problem: "SOP 与现场脱节，没有嵌入新人真实的工作场景。",
          },
          {
            id: "f4",
            stage: "handle",
            problem: "高风险判断与一般检索混在一起，人机责任边界没有定义。",
          },
          {
            id: "f5",
            stage: "writeback",
            problem: "缺回灌机制，新经验不回流组织。",
          },
        ],
        open_questions: [
          "哪些关键岗位目前只能由特定个人兜底？",
          "现场的判断记录现在以什么形式留存、能不能被检索？",
        ],
      },
      action: {
        first_step: {
          when: "本周",
          what: "把老师傅被问到的问题原样记下来，形成最值钱的知识底料",
          output: "一份老师傅问答记录表",
        },
        actions: [
          {
            finding_id: "f1",
            action: "把老师傅被问到的问题原样记录并归类，先把知识底料建起来，不等系统上线。",
            expected_output: "老师傅问答记录表",
          },
          {
            finding_id: "f2",
            action: "把关键判断的兜底路径写明，避免产能与响应受个人可用性牵制。",
            expected_output: "关键岗位兜底路径说明",
          },
          {
            finding_id: "f3",
            action: "按新人上手的真实步骤重排 SOP，并挂到实际作业入口上。",
            expected_output: "按新人上手路径重排的 SOP",
          },
          {
            finding_id: "f4",
            action: "把高风险判断与一般检索拆开——检索可自动给建议，高风险必须人工审核后再执行。",
            expected_output: "人机责任边界规则",
          },
          {
            finding_id: "f5",
            action: "定一条回灌路径：新经验必须回写进知识底料，回写人与触发时机都写死。",
            expected_output: "新经验回灌机制说明",
          },
        ],
        closing_loop: {
          identified: "说清哪些判断目前只有老师傅能做，现场靠盯人。",
          located: "定位到知识未沉淀与入口未嵌入两处断点。",
          handled: "先出可检索底料与分流规则，不等系统上线。",
          written_back: "新经验按回灌路径回流，规则版本可追溯。",
        },
      },
      policy: {
        opportunities: [
          {
            policy_id: "miit_lianyue_2026_343",
            title: "六部门《关于开展 2026 年度智能工厂梯度培育行动的通知》＋《智能工厂梯度培育要素条件(2026年版)》",
            doc_number: "工信厅联通装函〔2026〕343号",
            issued_on: "2026-07-15",
            original_basis: "原文口径",
            official_text:
              "卓越级智能工厂「应用人工智能技术场景比例**不低于 30%**」（2025 年版为 20%，一年抬 10 个点）；领航级不低于 60%。",
            official_source_url: "https://www.miit.gov.cn/",
            snapshot_date: POLICY_SNAPSHOT_DATE,
            interpretation_basis: "我方解读",
            our_reading:
              "智能工厂梯度培育（我方解读）；享受前提：AI 技术应用场景比例达标（卓越级不低于 30%／领航级不低于 60%，2026 年版）；下一步确认：向本地工信主管部门确认梯度培育申报口径、时间窗与所需材料；提示：要素条件的完整清单以 2026 年版原文为准，本卡不代为列举。",
          },
          {
            policy_id: "miit_lianke_2025_279",
            title: "八部门《「人工智能+制造」专项行动实施意见》",
            doc_number: "工信部联科〔2025〕279号",
            issued_on: "2025-12-25",
            original_basis: "原文口径",
            official_text:
              "2027 目标：「打造一批『懂智能、熟行业』的**赋能应用服务商**」；第十四条「发展赋能应用服务商」：行业模型调优、数据治理、安全保障、生态伙伴型服务商、优质服务商目录。",
            official_source_url:
              "https://www.miit.gov.cn/cms_files/filemanager/1226211233/attach/202512/8b6a31547603437db54d6596d33d04c4.pdf",
            snapshot_date: POLICY_SNAPSHOT_DATE,
            interpretation_basis: "我方解读",
            our_reading:
              "「人工智能+制造」行动（我方解读）；享受前提：服务商侧需具备行业模型调优与数据治理能力（279 号第十四条列举的服务商能力）",
          },
          {
            policy_id: "miit_minister_2026_03_05",
            title: "工信部部长「部长通道」公开表述",
            doc_number: "—",
            issued_on: "2026-03-05",
            original_basis: "原文口径",
            official_text:
              "「『人工智能+制造』是一个**必答题，不是一个选择题。**」同场披露：「我国规上制造业企业人工智能技术应用普及率**超 30%**，这是到去年底的数据」。",
            official_source_url:
              "https://www.miit.gov.cn/xwfb/bldhd/art/2026/art_e4b64e4dd78544708df400dd1042bdee.html",
            snapshot_date: POLICY_SNAPSHOT_DATE,
            interpretation_basis: "我方解读",
            our_reading:
              "规上制造业 AI 应用普及率现状基线（我方解读）；享受前提：规上制造业企业 AI 技术应用普及率已超 30%（部长通道披露口径，截至其发言时点）",
          },
        ],
      },
    },
    model: { source: "静态示例（非模型实时生成）" },
  },
}

const DELIVERY_SAMPLE: SampleCase = {
  caseId: "somwyn",
  badge: SAMPLE_BADGE_INTERNAL_DELIVERY,
  title: "小工厂外贸 · 获客体系",
  summary: "代号 somwyn（外贸 / 跨境获客）／小型外贸企业（小工厂背景）",
  attribution:
    "脱敏真实交付 · 代号化｜来源：内部真实交付件（G3 诊断报告），全部实体以代号 somwyn 指代；原件存本地真相层，不入仓库、不外发",
  note: "本例为外贸 / 跨境获客方向，按行业与资质口径未匹配到政策条目——报告不硬凑政策机会。",
  report: {
    version: REPORT_FORMAT_VERSION,
    prompt_version: STATIC_SAMPLE_VERSION,
    number_gate_version: STATIC_SAMPLE_VERSION,
    generated_at: "2026-11-12",
    layers: {
      situation: {
        headline: "被动等询盘、客户数据不自有、获客成本按坐席计费随规模膨胀：小工厂的获客体系还没长出来。",
        findings: [
          {
            id: "f1",
            stage: "identify",
            problem: "获客被动——等询盘加人工搜索，没有稳定的客户发现能力。",
          },
          {
            id: "f2",
            stage: "locate",
            problem: "客户数据沉淀在第三方平台内，关系不可迁移。",
          },
          {
            id: "f3",
            stage: "locate",
            problem: "获客成本按坐席与额度计费，规模越大越贵，对小厂是持续失血。",
          },
          {
            id: "f4",
            stage: "handle",
            problem: "自研 CRM 路径过重，与现有资源不匹配。",
          },
          {
            id: "f5",
            stage: "writeback",
            problem: "邮箱触达无纪律，长期会消耗域名信誉。",
          },
        ],
        open_questions: [
          "当前的获客投入按人力与订阅分别记了多少？",
          "客户接触记录现在存在哪里、能不能导出？",
        ],
      },
      action: {
        first_step: {
          when: "本周",
          what: "先算清成本结构——把人力耗时与订阅费折成单客成本，再与固定成本方案对比，决策依据是账不是感觉",
          output: "一份单客成本与固定成本方案的对比表",
        },
        actions: [
          {
            finding_id: "f1",
            action: "走可组合的自托管栈，把发现、数据、触达、编排拆成四层，先只建第一层，跑通再叠。",
            expected_output: "自托管栈第一层的落地方案",
          },
          {
            finding_id: "f2",
            action: "把客户接触记录沉淀到自有存储、保证可导出，不再被平台锁定。",
            expected_output: "自有客户数据存储与导出方案",
          },
          {
            finding_id: "f3",
            action: "按单客成本与固定成本两条口径对比，决定继续订阅还是转自建。",
            expected_output: "获客成本对比结论",
          },
          {
            finding_id: "f4",
            action: "明确暂不自研 CRM，只在现有工具上补最窄的一段。",
            expected_output: "暂缓自研 CRM 的取舍记录",
          },
          {
            finding_id: "f5",
            action: "给邮箱触达定纪律：频次、名单来源与退订处理都写死。",
            expected_output: "邮箱触达纪律说明",
          },
        ],
        closing_loop: {
          identified: "说清获客是等来的还是找来的。",
          located: "定位到客户发现能力缺失与客户数据不自有两处断点。",
          handled: "先建第一层，不做整套替换。",
          written_back: "触达与回复的真实结果回灌成判据，不用上游产出冒充整体成功。",
        },
      },
      policy: {
        opportunities: [],
      },
    },
    assessment_tier: "先做基础准备",
    model: { source: "静态示例（非模型实时生成）" },
  },
}

/** 全部示例案例（页面上可切换）。 */
export const SAMPLE_CASES: readonly SampleCase[] = [MANUFACTURING_SAMPLE, DELIVERY_SAMPLE]
