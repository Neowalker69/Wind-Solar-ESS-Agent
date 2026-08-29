# Contributing

感谢你关注 `wind-solar-ESS-Agent`。这是个人作品集和本地演示项目，欢迎提交可复现的问题、文档改进和范围清晰的代码贡献。

## 提交 Issue

提交前请先搜索已有 Issue，避免重复。Bug 报告请包含：

- 使用的操作系统、Python、Node.js 和 Docker 版本；
- 使用的部署方式和启用的 Compose profile；
- 最小复现步骤、预期结果和实际结果；
- 已脱敏的日志或错误信息。

不要在 Issue、截图或日志中提交 API Key、密码、Token、真实工业数据或内部网络信息。安全问题请按 `SECURITY.md` 私下报告。

## 提交 Pull Request

1. Fork 仓库并从 `main` 创建主题分支；
2. 保持改动范围单一，并为行为变更补充测试或文档；
3. 确认没有加入 `.env`、模型权重、缓存、日志或真实数据；
4. 在项目根目录运行 Python 测试；
5. 在 `apps/harness-control` 运行前端测试、类型检查和构建；
6. 清楚说明改动原因、验证方式和兼容性影响后再提交 PR。

```bash
uv sync --frozen --dev
uv run pytest -q

cd apps/harness-control
npm install
npm test
npm run typecheck
npm run build
```

提交 PR 即表示你有权提交相关代码和资产，并同意贡献内容按本仓库 MIT License 分发。原创视觉资产被修改或复用时，应保留 `ASSET-ATTRIBUTION.md` 中的出处说明。
