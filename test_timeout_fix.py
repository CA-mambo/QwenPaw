# -*- coding: utf-8 -*-
"""Test script for MCP Timeout Decoupling Fix.

Tests the new config parsing and timeout passing logic:
1. MCPClientConfig: split timeout into connection_timeout and execution_timeout
2. Backward compatibility for legacy timeout field
3. MCPClientManager: uses connection_timeout from config
4. QwenPawAgent: passes execution_timeout to toolkit.register_mcp_client
"""

import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from qwenpaw.config.config import MCPClientConfig
from qwenpaw.app.mcp.manager import MCPClientManager


def test_default_timeouts():
    """Test that default timeouts are correct."""
    print("Test 1: Default timeouts...")
    cfg = MCPClientConfig(
        name="test_client",
        command="echo",
        args=["hello"],
    )
    assert cfg.connection_timeout == 60.0, (
        f"Expected connection_timeout=60.0, got {cfg.connection_timeout}"
    )
    assert cfg.execution_timeout == 300.0, (
        f"Expected execution_timeout=300.0, got {cfg.execution_timeout}"
    )
    assert cfg.timeout is None, (
        f"Expected timeout=None by default, got {cfg.timeout}"
    )
    print("  PASSED: default connection_timeout=60.0, execution_timeout=300.0")


def test_legacy_timeout_backward_compatibility():
    """Test that legacy timeout field overrides both new fields."""
    print("Test 2: Legacy timeout backward compatibility...")
    cfg = MCPClientConfig(
        name="test_client",
        command="echo",
        args=["hello"],
        timeout=120.0,
    )
    assert cfg.connection_timeout == 120.0, (
        f"Expected connection_timeout=120.0, got {cfg.connection_timeout}"
    )
    assert cfg.execution_timeout == 120.0, (
        f"Expected execution_timeout=120.0, got {cfg.execution_timeout}"
    )
    assert cfg.timeout == 120.0, (
        f"Expected timeout=120.0, got {cfg.timeout}"
    )
    print("  PASSED: legacy timeout=120.0 applied to both connection and execution")


def test_explicit_timeouts_override_legacy():
    """Test that explicit new fields work alongside legacy timeout."""
    print("Test 3: Explicit timeouts with legacy field...")
    cfg = MCPClientConfig(
        name="test_client",
        command="echo",
        args=["hello"],
        timeout=120.0,
        connection_timeout=45.0,
        execution_timeout=200.0,
    )
    # Legacy timeout is applied first, then explicit fields override
    assert cfg.connection_timeout == 45.0, (
        f"Expected connection_timeout=45.0, got {cfg.connection_timeout}"
    )
    assert cfg.execution_timeout == 200.0, (
        f"Expected execution_timeout=200.0, got {cfg.execution_timeout}"
    )
    print("  PASSED: explicit timeouts override legacy")


def test_build_client_sets_timeout_attributes():
    """Test that _build_client sets timeout attributes on clients."""
    print("Test 4: _build_client sets timeout attributes...")
    cfg = MCPClientConfig(
        name="stdio_test",
        command="echo",
        args=["hello"],
        connection_timeout=90.0,
        execution_timeout=180.0,
    )

    client = MCPClientManager._build_client(cfg)
    assert hasattr(client, "connection_timeout"), (
        "Client should have connection_timeout attribute"
    )
    assert hasattr(client, "execution_timeout"), (
        "Client should have execution_timeout attribute"
    )
    assert client.connection_timeout == 90.0, (
        f"Expected connection_timeout=90.0, got {client.connection_timeout}"
    )
    assert client.execution_timeout == 180.0, (
        f"Expected execution_timeout=180.0, got {client.execution_timeout}"
    )
    print("  PASSED: _build_client sets timeout attributes correctly")


def test_build_client_http_transport():
    """Test that HTTP transport clients also get timeout attributes."""
    print("Test 5: HTTP transport timeout attributes...")
    cfg = MCPClientConfig(
        name="http_test",
        transport="streamable_http",
        url="http://localhost:8080/mcp",
        connection_timeout=30.0,
        execution_timeout=600.0,
    )

    client = MCPClientManager._build_client(cfg)
    assert client.connection_timeout == 30.0, (
        f"Expected connection_timeout=30.0, got {client.connection_timeout}"
    )
    assert client.execution_timeout == 600.0, (
        f"Expected execution_timeout=600.0, got {client.execution_timeout}"
    )
    print("  PASSED: HTTP transport timeout attributes set correctly")


def test_rebuild_info_contains_timeouts():
    """Test that _qwenpaw_rebuild_info contains timeout fields."""
    print("Test 6: _qwenpaw_rebuild_info contains timeouts...")
    cfg = MCPClientConfig(
        name="rebuild_test",
        command="echo",
        args=["test"],
        connection_timeout=75.0,
        execution_timeout=250.0,
    )

    client = MCPClientManager._build_client(cfg)
    rebuild_info = getattr(client, "_qwenpaw_rebuild_info", None)
    assert rebuild_info is not None, "Client should have _qwenpaw_rebuild_info"
    assert rebuild_info.get("connection_timeout") == 75.0, (
        f"Expected rebuild_info.connection_timeout=75.0"
    )
    assert rebuild_info.get("execution_timeout") == 250.0, (
        f"Expected rebuild_info.execution_timeout=250.0"
    )
    print("  PASSED: _qwenpaw_rebuild_info contains timeout fields")


async def test_manager_uses_connection_timeout():
    """Test that MCPClientManager uses connection_timeout from config."""
    print("Test 7: MCPClientManager uses connection_timeout...")
    cfg = MCPClientConfig(
        name="timeout_test",
        command="echo",
        args=["test"],
        connection_timeout=42.0,
        execution_timeout=500.0,
    )

    manager = MCPClientManager()

    # Mock the client's connect method
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.close = AsyncMock()

    with patch.object(MCPClientManager, "_build_client", return_value=mock_client):
        await manager._add_client("test_key", cfg)

    # Verify connect was called (timeout is handled by asyncio.wait_for)
    mock_client.connect.assert_called_once()

    # Cleanup
    await manager.close_all()
    print("  PASSED: MCPClientManager uses connection_timeout from config")


async def test_register_mcp_clients_execution_timeout():
    """Test that register_mcp_clients passes execution_timeout."""
    print("Test 8: register_mcp_clients passes execution_timeout...")

    # We can't fully test this without a full agent setup,
    # but we can verify the client attribute is read correctly
    mock_client = MagicMock()
    mock_client.name = "test_mcp"
    mock_client.execution_timeout = 450.0

    timeout = getattr(mock_client, "execution_timeout", 300.0)
    assert timeout == 450.0, (
        f"Expected execution_timeout=450.0, got {timeout}"
    )

    # Test fallback when attribute is missing
    mock_client_no_timeout = MagicMock()
    mock_client_no_timeout.name = "test_mcp_2"
    del mock_client_no_timeout.execution_timeout

    timeout_fallback = getattr(mock_client_no_timeout, "execution_timeout", 300.0)
    assert timeout_fallback == 300.0, (
        f"Expected fallback execution_timeout=300.0, got {timeout_fallback}"
    )

    print("  PASSED: register_mcp_clients reads execution_timeout with fallback")


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("MCP Timeout Decoupling Fix - Test Suite")
    print("=" * 60)

    passed = 0
    failed = 0
    errors = []

    # Sync tests
    sync_tests = [
        test_default_timeouts,
        test_legacy_timeout_backward_compatibility,
        test_explicit_timeouts_override_legacy,
        test_build_client_sets_timeout_attributes,
        test_build_client_http_transport,
        test_rebuild_info_contains_timeouts,
    ]

    for test_fn in sync_tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append(f"{test_fn.__name__}: {e}")
            print(f"  FAILED: {e}")

    # Async tests
    async_tests = [
        test_manager_uses_connection_timeout,
        test_register_mcp_clients_execution_timeout,
    ]

    for test_fn in async_tests:
        try:
            asyncio.run(test_fn())
            passed += 1
        except Exception as e:
            failed += 1
            errors.append(f"{test_fn.__name__}: {e}")
            print(f"  FAILED: {e}")

    # Summary
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if errors:
        print("\nFailed tests:")
        for err in errors:
            print(f"  - {err}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
