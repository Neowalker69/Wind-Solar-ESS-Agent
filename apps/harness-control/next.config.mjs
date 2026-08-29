import path from "node:path"

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: { externalDir: true },
  webpack(config) {
    const applicationNodeModules = path.resolve(process.cwd(), "node_modules")
    const configuredModules = config.resolve?.modules ?? ["node_modules"]
    config.resolve = {
      ...config.resolve,
      // 外部 frontend 源码必须复用 Harness Control 的 React 19 依赖图。
      modules: [applicationNodeModules, ...configuredModules.filter((entry) => entry !== applicationNodeModules)]
    }
    config.module.rules.push({ test: /\.glb$/i, type: "asset/resource" })
    return config
  }
}

export default nextConfig
