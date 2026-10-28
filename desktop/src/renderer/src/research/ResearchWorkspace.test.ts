import { describe, expect, it } from "vitest"

import {
  classifyExportPollResults,
  opportunitiesForSelectedSubject,
  shouldRescheduleExportPoll,
} from "./ResearchWorkspace"
import type { ResearchSubjectDto, ResearchSubjectType } from "./types"

function subject(id: string, type: ResearchSubjectType, parentId: string | null): ResearchSubjectDto {
  return {
    id,
    project_id: "project-1",
    parent_subject_id: parentId,
    subject_type: type,
    subject_key: id,
    name: id,
    description: "",
    sort_order: 0,
    status: "active",
    tracking_code: null,
    version: 1,
    links: [],
  }
}

describe("opportunitiesForSelectedSubject", () => {
  it("returns only opportunities directly attached to the selected object", () => {
    const subjects = [
      subject("project", "project", null),
      subject("sales", "department", "project"),
      subject("role", "role", "sales"),
      subject("project-opportunity", "opportunity", "project"),
      subject("sales-opportunity", "opportunity", "sales"),
      subject("role-opportunity", "opportunity", "role"),
    ]

    expect(opportunitiesForSelectedSubject(subjects, "sales").map((item) => item.id))
      .toEqual(["sales-opportunity"])
    expect(opportunitiesForSelectedSubject(subjects, "project").map((item) => item.id))
      .toEqual(["project-opportunity"])
  })
})

describe("classifyExportPollResults (J7b)", () => {
  it("marks a failed poll as failed instead of dropping it", () => {
    const outcome = classifyExportPollResults([null])
    expect(outcome.failed).toBe(true)
    expect(outcome.finished).toEqual([])
    expect(outcome.pending).toEqual([])
  })

  it("keeps still-running exports pending and finished ones separate", () => {
    const outcome = classifyExportPollResults([
      {
        id: "export-1",
        form_id: "form-1",
        form_name: "调研表一",
        status: "generating",
        version_number: null,
        failure_code: "",
        failure_message: "",
      },
      {
        id: "export-2",
        form_id: "form-2",
        form_name: "调研表二",
        status: "succeeded",
        version_number: 3,
        failure_code: "",
        failure_message: "",
      },
    ])
    expect(outcome.failed).toBe(false)
    expect(outcome.pending.map((item) => item.form_id)).toEqual(["form-1"])
    expect(outcome.finished).toEqual([
      { form_id: "form-2", form_name: "调研表二", status: "succeeded", version_number: 3, failure_message: "" },
    ])
  })

  it("reports a failed export as finished so the UI can clear the spinner", () => {
    const outcome = classifyExportPollResults([
      {
        id: "export-3",
        form_id: "form-3",
        form_name: "调研表三",
        status: "failed",
        version_number: null,
        failure_code: "boom",
        failure_message: "生成失败",
      },
    ])
    expect(outcome.failed).toBe(false)
    expect(outcome.finished[0].status).toBe("failed")
  })
})

describe("shouldRescheduleExportPoll (J7b)", () => {
  it("keeps polling after a failed round", () => {
    // 一次网络失败后必须继续下一轮，否则界面永久停在「生成中」
    expect(shouldRescheduleExportPoll({ failed: true })).toBe(true)
  })

  it("keeps polling after a successful round (still-running exports)", () => {
    expect(shouldRescheduleExportPoll({ failed: false })).toBe(true)
  })
})
