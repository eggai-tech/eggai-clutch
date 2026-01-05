# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
