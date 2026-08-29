import { describe, expect, it } from "@jest/globals"

import { splitStreamingMarkdown } from "../src/agent-workbench/markdown-blocks"

describe("Streaming Markdown blocks", () => {
  it("keeps only completed paragraphs in stable blocks", () => {
    expect(splitStreamingMarkdown("第一段。\n\n第二段正在生成")).toEqual({
      stableBlocks: ["第一段。"],
      activeBlock: "第二段正在生成"
    })
  })

  it("does not split blank lines inside an open fenced code block", () => {
    const source = "分析：\n\n```python\nvalue = 1\n\nprint(value)"

    expect(splitStreamingMarkdown(source)).toEqual({
      stableBlocks: ["分析："],
      activeBlock: "```python\nvalue = 1\n\nprint(value)"
    })
  })

  it("promotes a closed fenced block after a following boundary", () => {
    const source = "```text\nA\n\nB\n```\n\n结论"

    expect(splitStreamingMarkdown(source)).toEqual({
      stableBlocks: ["```text\nA\n\nB\n```"],
      activeBlock: "结论"
    })
  })
})
