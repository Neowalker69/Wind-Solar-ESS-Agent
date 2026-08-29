import "../../../frontend/src/index.css"
import "../src/agent-workbench/agent-streaming-workbench.css"
import "../src/auth/control-login.css"

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>
}
