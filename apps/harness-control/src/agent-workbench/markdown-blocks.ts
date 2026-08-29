export interface StreamingMarkdownBlocks {
  stableBlocks: string[]
  activeBlock: string
}

export function splitStreamingMarkdown(source: string): StreamingMarkdownBlocks {
  const stableBlocks: string[] = []
  const activeLines: string[] = []
  let fenceMarker = ""

  for (const line of source.replace(/\r\n/g, "\n").split("\n")) {
    const marker = line.trimStart().match(/^(`{3,}|~{3,})/)?.[1] ?? ""
    if (marker) {
      if (!fenceMarker) {
        fenceMarker = marker
      } else if (marker[0] === fenceMarker[0] && marker.length >= fenceMarker.length) {
        fenceMarker = ""
      }
    }

    if (!fenceMarker && !line.trim()) {
      const block = activeLines.join("\n").trimEnd()
      if (block) stableBlocks.push(block)
      activeLines.length = 0
      continue
    }
    activeLines.push(line)
  }

  return {
    stableBlocks,
    activeBlock: activeLines.join("\n").trimEnd()
  }
}
