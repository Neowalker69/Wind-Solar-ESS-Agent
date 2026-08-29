import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "@jest/globals"

const workbenchSource = readFileSync(
  path.resolve(process.cwd(), "src/agent-workbench/AgentStreamingWorkbench.tsx"),
  "utf8"
)

describe("Agent workbench focus isolation", () => {
  it("uses inert instead of hiding a potentially focused subtree", () => {
    expect(workbenchSource).toContain("inert={!open}")
    expect(workbenchSource).not.toContain("aria-hidden={!open}")
  })

  it("releases descendant focus before closing from buttons or Escape", () => {
    expect(workbenchSource).toContain("workbenchRef.current?.contains(activeElement)")
    expect(workbenchSource).toContain("activeElement.blur()")
    expect(workbenchSource).toContain("onClick={closeWorkbench}")
    expect(workbenchSource).toContain('if (event.key === "Escape") closeWorkbench()')
  })
})
