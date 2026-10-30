---
name: codeguard-context7-docs
description: >-
  External library and framework documentation assistant. Enforces version safety,
  parameter verification, and precedence hierarchy for FastAPI, Pydantic, SQLAlchemy,
  LangGraph, Gemini SDK, Next.js, and other ecosystem tools.
---

# Context7 Documentation Assistant

This skill guides querying and applying version-safe external library documentation.

## Core Rules

1. **Version Matching**:
   - Query Context7 documentation matching the exact version specified in `pyproject.toml` or `package.json`.
   - Never use bleeding-edge APIs if the installed version does not support them.
2. **Hierarchy Rule**:
   - `Project Architecture > Business Logic > Security Policy > Library Docs > Agent Suggestions`.
   - If official library documentation recommends patterns contrary to CodeGuard's security or architecture invariants, project invariants take precedence.
3. **Verified Ecosystem Packages**:
   - `FastAPI`: Router definitions, dependency injection (`Depends`), response models.
   - `Pydantic`: V2 `BaseModel`, `field_validator`, `model_validator`, `ConfigDict`.
   - `SQLAlchemy`: 2.0 style queries (`select()`), `mapped_column`, session handling.
   - `LangGraph`: `StateGraph`, `START`, `END`, conditional edges, state reducers.
   - `Google GenAI`: `google-genai` SDK, client configuration, model parameters.
   - `Next.js / React`: App router patterns, server/client components, hooks.
