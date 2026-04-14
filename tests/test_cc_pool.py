"""
Unit tests for CC Pool — uses mocked CCClient.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoservice.cc_pool import CCPool, PoolConfig, PooledInstance, load_pool_config


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class MockResultMessage:
    """Simulates a ResultMessage."""
    pass


def make_mock_client(alive: bool = True):
    """Create a mock CCClient that satisfies PoolableClient protocol."""
    client = MagicMock()
    client.is_healthy = MagicMock(return_value=alive)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.query = AsyncMock()

    async def _receive_response():
        yield MockResultMessage()

    client.receive_response = _receive_response
    return client


# ---------------------------------------------------------------------------
# PoolConfig tests
# ---------------------------------------------------------------------------

class TestPoolConfig:
    def test_defaults(self):
        config = PoolConfig()
        assert config.min_size == 1
        assert config.max_size == 4
        assert config.warmup_count == 1
        assert config.max_queries_per_instance == 50
        assert config.max_lifetime_seconds == 3600.0
        assert config.checkout_timeout == 30.0

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("CC_POOL_MIN_SIZE", "3")
        monkeypatch.setenv("CC_POOL_MAX_SIZE", "10")
        monkeypatch.setenv("CC_POOL_CHECKOUT_TIMEOUT", "60.5")
        monkeypatch.setenv("CC_POOL_PERMISSION_MODE", "default")

        config = load_pool_config(cwd="/nonexistent")
        assert config.min_size == 3
        assert config.max_size == 10
        assert config.checkout_timeout == 60.5
        assert config.permission_mode == "default"

    def test_yaml_loading(self, tmp_path, monkeypatch):
        """Load config from YAML file."""
        autoservice_dir = tmp_path / ".autoservice"
        autoservice_dir.mkdir()
        yaml_file = autoservice_dir / "config.local.yaml"
        yaml_file.write_text(
            "cc_pool:\n  min_size: 5\n  max_size: 20\n  model: claude-sonnet-4-5\n",
            encoding="utf-8",
        )

        config = load_pool_config(cwd=str(tmp_path))
        assert config.min_size == 5
        assert config.max_size == 20
        assert config.model == "claude-sonnet-4-5"


# ---------------------------------------------------------------------------
# PooledInstance tests
# ---------------------------------------------------------------------------

class TestPooledInstance:
    def test_is_healthy_alive(self):
        client = make_mock_client(alive=True)
        inst = PooledInstance(client=client, id="test-001")
        assert inst.is_healthy is True

    def test_is_healthy_dead(self):
        client = make_mock_client(alive=False)
        inst = PooledInstance(client=client, id="test-002")
        assert inst.is_healthy is False

    def test_is_healthy_exception(self):
        client = make_mock_client()
        client.is_healthy = MagicMock(side_effect=RuntimeError("broken"))
        inst = PooledInstance(client=client, id="test-003")
        assert inst.is_healthy is False

    def test_needs_recycling_query_count(self):
        config = PoolConfig(max_queries_per_instance=5)
        client = make_mock_client()
        inst = PooledInstance(client=client, id="test-004", query_count=5)
        assert inst.needs_recycling(config) is True

    def test_needs_recycling_age(self):
        config = PoolConfig(max_lifetime_seconds=10)
        client = make_mock_client()
        inst = PooledInstance(
            client=client, id="test-005",
            created_at=time.monotonic() - 20,
        )
        assert inst.needs_recycling(config) is True

    def test_no_recycling_needed(self):
        config = PoolConfig()
        client = make_mock_client()
        inst = PooledInstance(client=client, id="test-006")
        assert inst.needs_recycling(config) is False


# ---------------------------------------------------------------------------
# CCPool tests
# ---------------------------------------------------------------------------

class TestCCPool:
    @pytest.fixture
    def pool_config(self):
        return PoolConfig(
            min_size=1,
            max_size=3,
            warmup_count=2,
            health_check_interval=100,  # Long interval to avoid interference
            checkout_timeout=2.0,
        )

    @pytest.mark.asyncio
    async def test_start_creates_warm_instances(self, pool_config):
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(pool_config)
            await pool.start()
            try:
                assert pool.size == 2
                assert pool.available_count == 2
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_checkout_returns_instance(self, pool_config):
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(pool_config)
            await pool.start()
            try:
                inst = await pool.checkout()
                assert inst is not None
                assert inst.is_healthy
                assert pool.available_count == 1  # One still in queue
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_checkout_checkin_cycle(self, pool_config):
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(pool_config)
            await pool.start()
            try:
                inst = await pool.checkout()
                assert pool.available_count == 1
                await pool.checkin(inst)
                assert pool.available_count == 2
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_context_manager(self, pool_config):
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(pool_config)
            await pool.start()
            try:
                async with pool.acquire() as inst:
                    assert inst.is_healthy
                    assert pool.available_count == 1
                # After context exit, instance returned
                assert pool.available_count == 2
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_on_demand_creation(self):
        """When queue is empty but under max, creates on demand."""
        config = PoolConfig(min_size=0, max_size=2, warmup_count=0, health_check_interval=100)
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(config)
            await pool.start()
            try:
                assert pool.size == 0
                inst = await pool.checkout()
                assert pool.size == 1
                assert inst.is_healthy
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_pool_exhaustion_timeout(self):
        """When at max_size and all checked out, timeout."""
        config = PoolConfig(min_size=0, max_size=1, warmup_count=1, health_check_interval=100, checkout_timeout=0.5)
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(config)
            await pool.start()
            try:
                _ = await pool.checkout()  # Take the only one
                with pytest.raises(TimeoutError):
                    await pool.checkout(timeout=0.2)
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_checkin_recycles_unhealthy(self):
        """Unhealthy instances are destroyed on checkin."""
        config = PoolConfig(min_size=0, max_size=2, warmup_count=1, health_check_interval=100)
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(config)
            await pool.start()
            try:
                inst = await pool.checkout()
                # Mark as unhealthy
                inst.client.is_healthy.return_value = False
                assert inst.is_healthy is False
                await pool.checkin(inst)
                # Instance was destroyed, not returned to queue
                assert inst.id not in pool._all_instances
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_checkin_recycles_overused(self):
        """Instances exceeding max_queries_per_instance are recycled."""
        config = PoolConfig(min_size=0, max_size=2, warmup_count=1,
                            max_queries_per_instance=3, health_check_interval=100)
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(config)
            await pool.start()
            try:
                inst = await pool.checkout()
                inst.query_count = 5
                await pool.checkin(inst)
                assert inst.id not in pool._all_instances
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_all(self, pool_config):
        clients = []
        def track_client(cfg):
            c = make_mock_client()
            clients.append(c)
            return c

        with patch("autoservice.cc_pool.create_cc_client", side_effect=track_client):
            pool = CCPool(pool_config)
            await pool.start()
            await pool.shutdown()

            assert pool.size == 0
            for c in clients:
                c.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_not_started(self):
        """Shutdown on a pool that was never started is a no-op."""
        pool = CCPool()
        await pool.shutdown()  # Should not raise

    @pytest.mark.asyncio
    async def test_checkout_not_started(self):
        """Checkout before start raises RuntimeError."""
        pool = CCPool()
        with pytest.raises(RuntimeError, match="not running"):
            await pool.checkout()

    @pytest.mark.asyncio
    async def test_status(self, pool_config):
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(pool_config)
            await pool.start()
            try:
                status = pool.status()
                assert status["started"] is True
                assert status["total"] == 2
                assert status["available"] == 2
                assert status["max_size"] == 3
                assert len(status["instances"]) == 2
            finally:
                await pool.shutdown()

    @pytest.mark.asyncio
    async def test_query_convenience(self):
        """Pool.query() checks out, queries, and checks in."""
        config = PoolConfig(min_size=0, max_size=1, warmup_count=1, health_check_interval=100)
        with patch("autoservice.cc_pool.create_cc_client", side_effect=lambda cfg: make_mock_client()):
            pool = CCPool(config)
            await pool.start()
            try:
                messages = []
                async for msg in pool.query("test prompt"):
                    messages.append(msg)
                assert len(messages) == 1
                assert isinstance(messages[0], MockResultMessage)
                # Instance should be back in pool
                assert pool.available_count == 1
            finally:
                await pool.shutdown()
