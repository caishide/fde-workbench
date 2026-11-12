// @vitest-environment jsdom
// 获客诊断 T-13′：工具内示例报告页用例（公开面）。
//
// 覆盖：角标纪律（R-6 固定文案：示例案例 · 据公开案例整理／脱敏真实交付 ·
// 代号化）／「非实时诊断结果」声明在场／示例内容无分数无金额（R-1、R-4）／
// stage 闭集英文代号翻中文、未命中值原样透传／案例切换／报告底部写「示例
// 整理日期」而不是「生成于」／去测算入口。
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"

import { PublicDiagnosticSamplePage } from "../../src/renderer/src/diagnostics/PublicDiagnosticSamplePage"
import { ReportView, stageLabel } from "../../src/renderer/src/diagnostics/ReportView"
import {
  SAMPLE_BADGE_INTERNAL_DELIVERY,
  SAMPLE_BADGE_PUBLIC_CASE,
  SAMPLE_CASES,
} from "../../src/renderer/src/diagnostics/sampleReport"

afterEach(() => {
  cleanup()
})

describe("工具内示例报告页（公开面）", () => {
  it("在页面上同时给出角标与「非实时诊断结果」声明", async () => {
    render(<PublicDiagnosticSamplePage />)

    expect(await screen.findByText(SAMPLE_BADGE_PUBLIC_CASE)).toBeVisible()
    expect(screen.getByText("示例内容 · 非实时诊断结果")).toBeVisible()
    expect(screen.getByText(/不是对任何企业的实时诊断/)).toBeVisible()
  })

  it("报告底部写「示例整理日期」而不是「生成于」", async () => {
    render(<PublicDiagnosticSamplePage />)

    expect(await screen.findByText(/示例整理日期 2026-11-12（非实时生成）/)).toBeVisible()
    expect(screen.queryByText(/生成于/)).not.toBeInTheDocument()
  })

  it("示例报告正文不含分数、不含评分式百分比（R-1／R-4）", async () => {
    render(<PublicDiagnosticSamplePage />)

    // 只取报告本体（页面顶部的声明文案本身会提到「评分」二字，不在禁词域内）。
    const report = document.querySelector(".diag-report")
    expect(report).not.toBeNull()
    const body = report?.textContent ?? ""
    // 分数形态：xx/100（真相层原始卡片带 41/100、32/100 等分数，仓内示例不得照搬）
    expect(body).not.toMatch(/\d+\s*\/\s*100/)
    expect(body).not.toContain("评分")
    expect(body).not.toContain("得分")
    // 允许出现的百分比只有政策引文里的口径比例，逐个核对（不多不少）
    const percents = [...new Set((body.match(/\d{1,3}\s*%/g) ?? []).map((hit) => hit.replace(/\s+/g, "")))]
    expect([...percents].sort()).toEqual(["20%", "30%", "60%"])
  })

  it("政策条目按原文口径与我方解读双层呈现，并带官方出处与快照日期", async () => {
    render(<PublicDiagnosticSamplePage />)

    expect((await screen.findAllByText("原文口径")).length).toBeGreaterThan(0)
    expect(screen.getAllByText("我方解读").length).toBeGreaterThan(0)
    expect(screen.getAllByText(/快照 2026-10-19/).length).toBeGreaterThan(0)
    const links = screen.getAllByRole("link")
    expect(links.some((link) => link.getAttribute("href")?.includes("miit.gov.cn"))).toBe(true)
  })

  it("可切换到脱敏真实交付案例，角标随之切换", async () => {
    const user = userEvent.setup()
    render(<PublicDiagnosticSamplePage />)

    expect(await screen.findByText(SAMPLE_BADGE_PUBLIC_CASE)).toBeVisible()
    await user.click(screen.getByRole("button", { name: "小工厂外贸 · 获客体系" }))

    expect(await screen.findByText(SAMPLE_BADGE_INTERNAL_DELIVERY)).toBeVisible()
    expect(screen.queryByText(SAMPLE_BADGE_PUBLIC_CASE)).not.toBeInTheDocument()
  })

  it("脱敏真实交付案例按行业与资质口径不硬凑政策机会", async () => {
    const user = userEvent.setup()
    render(<PublicDiagnosticSamplePage />)

    await user.click(screen.getByRole("button", { name: "小工厂外贸 · 获客体系" }))

    expect(await screen.findByText(/未匹配到政策条目/)).toBeVisible()
    expect(screen.queryByText("政策与申报机会")).not.toBeInTheDocument()
  })

  it("给出去测算的入口", async () => {
    render(<PublicDiagnosticSamplePage />)

    const link = await screen.findByRole("link", { name: "去做测算" })
    expect(link).toHaveAttribute("href", "#diagnostics")
  })
})

describe("报告渲染的阶段标签映射", () => {
  it("闭环四步的闭集代号翻成中文", () => {
    expect(stageLabel("identify")).toBe("识别")
    expect(stageLabel("locate")).toBe("定位")
    expect(stageLabel("handle")).toBe("处置")
    expect(stageLabel("writeback")).toBe("回写")
  })

  it("未命中闭集的值原样透传（不臆造译名）", () => {
    expect(stageLabel("报价与方案")).toBe("报价与方案")
    expect(stageLabel("")).toBe("")
  })

  it("示例报告的阶段以中文标签呈现", async () => {
    render(<PublicDiagnosticSamplePage />)

    expect(await screen.findByText("识别")).toBeVisible()
    expect(screen.getAllByText("定位").length).toBeGreaterThan(0)
    expect(screen.getByText("处置")).toBeVisible()
    expect(screen.getByText("回写")).toBeVisible()
  })

  it("页面不出现英文闭环代号（活体报告同样受益）", async () => {
    render(<PublicDiagnosticSamplePage />)

    await screen.findByText(SAMPLE_BADGE_PUBLIC_CASE)
    expect(screen.queryByText("identify")).not.toBeInTheDocument()
    expect(screen.queryByText("locate")).not.toBeInTheDocument()
    expect(screen.queryByText("handle")).not.toBeInTheDocument()
    expect(screen.queryByText("writeback")).not.toBeInTheDocument()
  })

  it("ReportView 对自由文本阶段名原样透传（活体报告不回归）", () => {
    render(
      <ReportView
        report={{
          ...SAMPLE_CASES[0].report,
          layers: {
            ...SAMPLE_CASES[0].report.layers,
            situation: {
              ...SAMPLE_CASES[0].report.layers.situation,
              findings: [{ id: "f1", problem: "报价要问老工程师", stage: "报价与方案" }],
            },
          },
        }}
      />,
    )

    expect(screen.getByText("报价与方案")).toBeVisible()
    expect(screen.queryByText("identify")).not.toBeInTheDocument()
  })
})
