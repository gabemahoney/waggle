---
id: features.bees-h8w
type: t1
title: Fix incorrect entry point in examples/mcp-config.json
parent: features.bees-n6y
children:
- features.bees-4wm
- features.bees-y6e
- features.bees-9ie
created_at: '2026-02-12T12:12:37.327532'
updated_at: '2026-02-12T12:27:40.262167'
priority: 0
status: completed
bees_version: '1.1'
---

## What

`examples/mcp-config.json:7` references `"waggle-server"` as the poetry script, but `pyproject.toml:18` defines the entry point as `waggle`. Anyone copying the example config would get a "script not found" error.

## How

Change `"waggle-server"` to `"waggle"` on line 7 of `examples/mcp-config.json`.

## Files
- `examples/mcp-config.json`
