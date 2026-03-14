# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-03-14

### Changed
- Release workflows: migrate from GITHUB_TOKEN to GitHub App token with auto-publish on merge
- Pin all GitHub Actions to SHA digests for supply chain security
- Update actions/checkout v4 to v6, codecov/codecov-action v4 to v5
- CI now uses uv for deterministic dependency resolution with uv.lock
- Replace softprops/action-gh-release with native gh CLI

### Fixed
- Script injection vulnerabilities in release workflow version inputs
- Skip-changelog label now properly bypasses changelog check for pre-release PRs
- EOF heredoc injection in changelog extraction (random delimiter)
- Add PyPI pre-flight check for idempotent publish retries
- Add failure notification job (auto-creates GitHub issue on release failure)

## [0.2.0] - 2026-01-05

### Added
- `llms.txt` for AI assistant documentation
- `context7.json` for Context7 integration

## [0.1.0] - 2025-01-02

### Added
- Initial release
- Multi-strategy agent orchestration (SEQUENTIAL, ROUND_ROBIN, GRAPH, SELECTOR)
- `Clutch` class for pipeline orchestration
- `ClutchTask` for async task handling with submit/run/stream
- `StepEvent` for streaming step results
- `Terminate` and `Handover` control flow exceptions
- Pydantic model support for typed data flow
- Distributed mode support via EggAI transports
- Hooks: `on_request`, `on_response`, `on_step`
- Examples: RAG pipeline, support triage, code review
