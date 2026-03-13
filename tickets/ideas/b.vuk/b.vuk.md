---
id: b.vuk
type: bee
title: Allow `claude mcp add` instead of manual MCP configuration
parent: null
children:
- t1.vuk.w7
- t1.vuk.srd
egg: null
created_at: '2026-03-12T18:28:10.338760'
status: pupa
schema_version: '0.1'
guid: vuk188nnvdufqwb5zte1kxssnbo4h7d2
---

## Idea

Replace the current manual MCP server configuration process with support for using `claude mcp add` to register MCP servers.

## Current State

MCP servers are configured manually (likely editing JSON config files directly).

## Desired Outcome

Users can run `claude mcp add <server>` to add MCP servers, which is the standard Claude Code workflow for managing MCP integrations.
