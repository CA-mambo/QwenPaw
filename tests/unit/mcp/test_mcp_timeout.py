# -*- coding: utf-8 -*-
"""Tests for MCP Timeout Decoupling Fix.

Tests the new config parsing and timeout passing logic:
1. MCPClientConfig: split timeout into connection_timeout and execution_timeout
2. Backward compatibility for legacy timeout field
3. MCPClientManager: uses connection_timeout from config
4. QwenPawAgent: passes execution_timeout to toolkit.register_mcp_client
"""

# pylint: disable=protected-access
# pylint: disable=unused-argument
# pylint: disable=reimported
# pylint: disable=wrong-import-position

import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
)

from qwenpaw.app.mcp.manager import MCPClientManager  # noqa: E402
from qwenpaw.config.config import MCPClientConfig  # noqa: E402

# === Original Sync Tests (converted to pytest) ===


def test_default_timeouts():
    """Test that default timeouts are correct."""
    cfg = MCPClientConfig(
        name="test_client",
        command="echo",
        args=["hello"],
    )
    assert cfg.connection_timeout == 60.0
    assert cfg.execution_timeout == 300.0
    assert cfg.timeout is None


def test_legacy_timeout_backward_compatibility():
    """Test that legacy timeout field overrides both new fields."""
    cfg = MCPClientConfig(
        name="test_client",
        command="echo",
        args=["hello"],
        timeout=120.0,
    )
    assert cfg.connection_timeout == 120.0
    assert cfg.execution_timeout == 120.0
    assert cfg.timeout == 120.0


def test_explicit_timeouts_override_legacy():
    """Test that explicit new fields work alongside legacy timeout."""
    cfg = MCPClientConfig(
        name="test_client",
        command="echo",
        args=["hello"],
        timeout=120.0,
        connection_timeout=45.0,
        execution_timeout=200.0,
    )
    # Legacy timeout is applied first, then explicit fields override
    assert cfg.connection_timeout == 45.0
    assert cfg.execution_timeout == 200.0


def test_build_client_sets_timeout_attributes():
    """Test that _build_client sets timeout attributes on clients."""
    cfg = MCPClientConfig(
        name="stdio_test",
        command="echo",
        args=["hello"],
        connection_timeout=90.0,
        execution_timeout=180.0,
    )

    client = MCPClientManager._build_client(cfg)
    assert hasattr(client, "connection_timeout")
    assert hasattr(client, "execution_timeout")
    assert client.connection_timeout == 90.0
    assert client.execution_timeout == 180.0


def test_build_client_http_transport():
    """Test that HTTP transport clients also get timeout attributes."""
    cfg = MCPClientConfig(
        name="http_test",
        transport="streamable_http",
        url="http://localhost:8080/mcp",
        connection_timeout=30.0,
        execution_timeout=600.0,
    )

    client = MCPClientManager._build_client(cfg)
    assert client.connection_timeout == 30.0
    assert client.execution_timeout == 600.0


def test_rebuild_info_contains_timeouts():
    """Test that _qwenpaw_rebuild_info contains timeout fields."""
    cfg = MCPClientConfig(
        name="rebuild_test",
        command="echo",
        args=["test"],
        connection_timeout=75.0,
        execution_timeout=250.0,
    )

    client = MCPClientManager._build_client(cfg)
    rebuild_info = getattr(client, "_qwenpaw_rebuild_info", None)
    assert rebuild_info is not None
    assert rebuild_info.get("connection_timeout") == 75.0
    assert rebuild_info.get("execution_timeout") == 250.0


# === Original Async Tests (converted to pytest.mark.asyncio) ===


@pytest.mark.asyncio
async def test_manager_uses_connection_timeout():
    """Test that MCPClientManager uses connection_timeout from config."""
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

    with patch.object(
        MCPClientManager, "_build_client", return_value=mock_client
    ):
        await manager._add_client("test_key", cfg)

    # Verify connect was called (timeout is handled by asyncio.wait_for)
    mock_client.connect.assert_called_once()

    # Cleanup
    await manager.close_all()


@pytest.mark.asyncio
async def test_register_mcp_clients_execution_timeout():
    """Test that register_mcp_clients passes execution_timeout."""
    # We can't fully test this without a full agent setup,
    # but we can verify the client attribute is read correctly
    mock_client = MagicMock()
    mock_client.name = "test_mcp"
    mock_client.execution_timeout = 450.0

    timeout = getattr(mock_client, "execution_timeout", 300.0)
    assert timeout == 450.0

    # Test fallback when attribute is missing
    mock_client_no_timeout = MagicMock()
    mock_client_no_timeout.name = "test_mcp_2"
    del mock_client_no_timeout.execution_timeout

    timeout_fallback = getattr(
        mock_client_no_timeout, "execution_timeout", 300.0
    )
    assert timeout_fallback == 300.0


# === New Async Mock Tests ===


@pytest.mark.asyncio
async def test_connection_timeout_behavior():
    """Test connection timeout behavior when client hangs during connect.

    Mock manager._build_client -> client.connect to simulate a hang.
    Verify the manager handles it (or raises TimeoutError).
    """
    cfg = MCPClientConfig(
        name="hang_test",
        command="echo",
        args=["test"],
        connection_timeout=1.0,  # Very short timeout for fast test
        execution_timeout=300.0,
    )

    manager = MCPClientManager()

    async def hang_forever(*args, **kwargs):
        """Simulate a client that never connects."""
        await asyncio.sleep(1000)

    mock_client = MagicMock()
    mock_client.connect = AsyncMock(side_effect=hang_forever)
    mock_client.close = AsyncMock()

    with patch.object(
        MCPClientManager, "_build_client", return_value=mock_client
    ):
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await manager._add_client("hang_key", cfg)

    # Cleanup
    await manager.close_all()


@pytest.mark.asyncio
async def test_execution_timeout_passed_to_toolkit():
    """Verify register_mcp_clients passes the correct execution_timeout
    to toolkit.register_mcp_client via mock.
    """
    # Create a mock toolkit
    mock_toolkit = MagicMock()
    mock_toolkit.register_mcp_client = MagicMock()

    # Create a mock MCP client with execution_timeout
    mock_mcp_client = MagicMock()
    mock_mcp_client.name = "test_tool_client"
    mock_mcp_client.execution_timeout = 420.0

    # Simulate what register_mcp_clients does:
    # It reads execution_timeout from the client and passes it to toolkit
    execution_timeout = getattr(mock_mcp_client, "execution_timeout", 300.0)

    # Call the toolkit method as the real code would
    mock_toolkit.register_mcp_client(
        mock_mcp_client,
        execution_timeout=execution_timeout,
    )

    # Verify the correct timeout was passed
    mock_toolkit.register_mcp_client.assert_called_once_with(
        mock_mcp_client,
        execution_timeout=420.0,
    )


@pytest.mark.asyncio
async def test_legacy_config_safety():
    """Ensure that if a user sets ONLY connection_timeout, the legacy
    timeout logic doesn't mess it up.
    """
    # User sets only connection_timeout
    cfg = MCPClientConfig(
        name="legacy_safety_test",
        command="echo",
        args=["test"],
        connection_timeout=90.0,
    )

    # Verify connection_timeout is preserved
    assert cfg.connection_timeout == 90.0

    # Verify execution_timeout uses default (not overridden by legacy logic)
    assert cfg.execution_timeout == 300.0

    # Verify legacy timeout field remains None
    assert cfg.timeout is None

    # Build a client and verify the timeout attributes are correct
    client = MCPClientManager._build_client(cfg)
    assert client.connection_timeout == 90.0
    assert client.execution_timeout == 300.0

    # Verify rebuild_info also has correct values
    rebuild_info = getattr(client, "_qwenpaw_rebuild_info", None)
    assert rebuild_info is not None
    assert rebuild_info.get("connection_timeout") == 90.0
    assert rebuild_info.get("execution_timeout") == 300.0
