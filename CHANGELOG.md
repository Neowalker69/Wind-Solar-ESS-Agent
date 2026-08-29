# Changelog

All notable public changes to `wind-solar-ESS-Agent` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning where practical.

## [Unreleased]

### Added

- GitHub Actions CI for Python and Harness Control;
- Dependabot configuration for Python, npm, Docker and GitHub Actions;
- contributor guidance, asset attribution and synthetic-data notices.

### Changed

- repository identity updated to `wind-solar-ESS-Agent`;
- default API and Control ports restricted to the local loopback interface;
- Harness Control tests made self-contained for fresh GitHub clones.

## [0.1.0] - 2026-08-29

### Added

- Agent Runtime, context compilation, workflow, memory, tool registry and audit-oriented event stream;
- explicit DeepSeek and Alibaba Cloud Bailian model providers;
- optional RAG corpus with local reranker deployment profile;
- optional Harness Control digital-twin workbench;
- Docker Compose deployment for API Gateway, PostgreSQL and Redis.

[Unreleased]: https://github.com/Neowalker69/wind-solar-ESS-Agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Neowalker69/wind-solar-ESS-Agent/releases/tag/v0.1.0
