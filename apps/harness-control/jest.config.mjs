/** @type {import('jest').Config} */
const config = {
  testEnvironment: "node",
  testMatch: ["<rootDir>/tests/**/*.test.ts", "<rootDir>/tests/**/*.test.tsx"],
  extensionsToTreatAsEsm: [".ts", ".tsx"],
  transform: {
    "^.+\\.[tj]sx?$": [
      "@swc/jest",
      {
        jsc: {
          parser: { syntax: "typescript", tsx: true },
          transform: { react: { runtime: "automatic" } }
        },
        module: { type: "es6" }
      }
    ]
  },
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],
  collectCoverageFrom: [
    "src/agent-workbench/agent-stream-client.ts",
    "src/agent-workbench/agent-workbench-store.ts",
    "src/agent-workbench/markdown-blocks.ts",
    "src/agent-workbench/sse-parser.ts",
    "src/agent-workbench/stream-buffer.ts",
    "src/agent-workbench/stream-reducer.ts",
    "src/agent-workbench/components/AgentExecutionStatus.tsx",
    "src/agent-workbench/components/StreamMarkdownRenderer.tsx"
  ],
  coverageProvider: "v8",
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80
    }
  }
}

export default config
