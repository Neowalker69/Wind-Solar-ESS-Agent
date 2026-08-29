"use client"

import { memo, useMemo } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { splitStreamingMarkdown } from "../markdown-blocks"

const MarkdownBlock = memo(function MarkdownBlock({ source }: { source: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a>
      }}
    >
      {source}
    </ReactMarkdown>
  )
})

export function StreamMarkdownRenderer({
  content,
  completed
}: {
  content: string
  completed: boolean
}) {
  const blocks = useMemo(() => splitStreamingMarkdown(content), [content])

  if (completed) {
    return <div className="agent-markdown"><MarkdownBlock source={content} /></div>
  }
  return (
    <div className="agent-markdown agent-markdown-streaming">
      {blocks.stableBlocks.map((block, index) => (
        <MarkdownBlock key={`${index}:${block.slice(0, 32)}`} source={block} />
      ))}
      {blocks.activeBlock && <div className="agent-markdown-active">{blocks.activeBlock}</div>}
    </div>
  )
}
