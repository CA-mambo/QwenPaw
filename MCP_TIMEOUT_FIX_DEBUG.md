# MCP Timeout Decoupling Fix

## Problem

Previously, `MCPClientConfig` had a single `timeout` field that was ambiguously used for both:
1. **Connection timeout**: How long to wait when establishing a connection to an MCP server
2. **Execution timeout**: How long to allow MCP tool calls to run

This caused issues where a short timeout value would cause long-running MCP tool calls to fail prematurely, while a long timeout would cause the application to hang during connection issues.

## Solution

Decoupled the single `timeout` field into two distinct fields:

| Field | Default | Purpose |
|---|---|---|
| `connection_timeout` | 60s | Timeout for establishing MCP client connection |
| `execution_timeout` | 300s (5min) | Timeout for MCP tool execution |

## Changes Made

### 1. `src/qwenpaw/config/config.py` — `MCPClientConfig`

- Added `connection_timeout: float` (default 60.0)
- Added `execution_timeout: float` (default 300.0)
- Kept `timeout: Optional[float]` as a **legacy field** for backward compatibility
- Added `_apply_legacy_timeout` model validator: if the legacy `timeout` field is set, it only overrides the new fields when they are at their default values. Explicit values for `connection_timeout`/`execution_timeout` take precedence.

### 2. `src/qwenpaw/app/mcp/manager.py` — `MCPClientManager`

- `replace_client()` and `_add_client()`: Now extract `connection_timeout` from `client_config` instead of accepting a hardcoded `timeout` parameter
- `_build_client()`: Attaches both `connection_timeout` and `execution_timeout` as attributes on the created client instance, and stores them in `_qwenpaw_rebuild_info` for client recovery/rebuild scenarios

### 3. `src/qwenpaw/agents/react_agent.py` — `QwenPawAgent`

- `register_mcp_clients()`: Now reads `execution_timeout` from the client attribute (`getattr(client, "execution_timeout", 300.0)`) and passes it to `toolkit.register_mcp_client()`
- Fixed a typo: `exeution_timeout` → `execution_timeout` in the recovery path
- `_rebuild_mcp_client()`: Restores `connection_timeout` and `execution_timeout` attributes on rebuilt clients from `_qwenpaw_rebuild_info`

### 4. `src/qwenpaw/agents/tools/file_search.py`

- **No changes needed**. The `_GREP_TIMEOUT` (30s) and `_GLOB_TIMEOUT` (15s) constants are tool-level safeguards for file search operations, unrelated to MCP timeouts.

## Backward Compatibility

The legacy `timeout` field is fully supported:

```python
# Old config (still works):
{"name": "my_mcp", "command": "npx", "args": ["-y", "some-mcp"], "timeout": 120}
# → connection_timeout=120, execution_timeout=120

# New config (recommended):
{"name": "my_mcp", "command": "npx", "args": ["-y", "some-mcp"], 
 "connection_timeout": 60, "execution_timeout": 300}

# Mixed (new fields take precedence):
{"name": "my_mcp", "command": "npx", "args": ["-y", "some-mcp"],
 "timeout": 120, "connection_timeout": 45}
# → connection_timeout=45 (explicit wins), execution_timeout=120 (from legacy)
```

## Test Results

All 8 tests passed:

```
Test 1: Default timeouts...
  PASSED: default connection_timeout=60.0, execution_timeout=300.0
Test 2: Legacy timeout backward compatibility...
  PASSED: legacy timeout=120.0 applied to both connection and execution
Test 3: Explicit timeouts with legacy field...
  PASSED: explicit timeouts override legacy
Test 4: _build_client sets timeout attributes...
  PASSED: _build_client sets timeout attributes correctly
Test 5: HTTP transport timeout attributes...
  PASSED: HTTP transport timeout attributes set correctly
Test 6: _qwenpaw_rebuild_info contains timeouts...
  PASSED: _qwenpaw_rebuild_info contains timeout fields
Test 7: MCPClientManager uses connection_timeout...
  PASSED: MCPClientManager uses connection_timeout from config
Test 8: register_mcp_clients passes execution_timeout...
  PASSED: register_mcp_clients reads execution_timeout with fallback
Results: 8 passed, 0 failed, 8 total
```

## Architecture Diagram

```
Config (config.json)
  └── mcp.clients.{key}
        ├── connection_timeout: 60    ──┐
        ├── execution_timeout: 300      ──┤
        └── timeout: 120 (legacy)     ──┤
                                        │
MCPClientManager                        │
  ├── _add_client()        ◄────────────┘ (uses connection_timeout)
  ├── replace_client()     ◄────────────┘ (uses connection_timeout)
  └── _build_client()      ─────────────► sets client.connection_timeout
                                          sets client.execution_timeout

QwenPawAgent
  └── register_mcp_clients()
        └── toolkit.register_mcp_client(client, execution_timeout=...)
                                          ▲
                                          └── reads client.execution_timeout
```
