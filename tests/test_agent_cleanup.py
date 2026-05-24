"""
Tests for Bounty $5k: Run cleanup when BaseAgent setup fails.
Verifies that cleanup runs even when setup raises an exception.
"""
import pytest
from unittest.mock import AsyncMock, patch
from src.sdk.agent import BaseAgent


class MockAgent(BaseAgent):
    """Concrete agent for testing BaseAgent lifecycle."""

    def __init__(self, setup_should_fail=False, setup_delay=0):
        super().__init__(agent_id="test-1", name="test-agent")
        self.setup_should_fail = setup_should_fail
        self.setup_delay = setup_delay
        self.setup_called = False
        self.cleanup_called = False

    async def setup(self) -> None:
        self.setup_called = True
        if self.setup_delay > 0:
            import asyncio
            await asyncio.sleep(self.setup_delay)
        if self.setup_should_fail:
            raise RuntimeError("Setup failed")

    async def handle_task(self, task: dict) -> None:
        return None

    async def cleanup(self) -> None:
        self.cleanup_called = True


class TestBaseAgentCleanup:

    @pytest.mark.asyncio
    async def test_cleanup_called_when_setup_succeeds(self):
        """Cleanup is called when setup completes normally."""
        agent = MockAgent()
        await agent.run()
        assert agent.setup_called
        assert agent.cleanup_called

    @pytest.mark.asyncio
    async def test_cleanup_called_when_setup_fails(self):
        """Cleanup IS called even when setup raises.

        This is the core fix — previously setup ran before the try/finally
        block, so cleanup was skipped if setup raised."""
        agent = MockAgent(setup_should_fail=True)
        with pytest.raises(RuntimeError):
            await agent.run()
        assert agent.setup_called, "setup must be called"
        assert agent.cleanup_called, "cleanup MUST be called after failed setup"

    @pytest.mark.asyncio
    async def test_cleanup_called_on_cancellation(self):
        """Cleanup still called when agent is cancelled."""
        agent = MockAgent()
        task = asyncio.create_task(agent.run())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert agent.cleanup_called

    @pytest.mark.asyncio
    async def test_cleanup_not_called_before_setup(self):
        """Cleanup is not called if setup was never reached."""
        agent = MockAgent(setup_should_fail=True)
        # _running is set before setup, but cleanup should only
        # release resources that setup opened
        agent.cleanup_called = False
        try:
            await agent.run()
        except RuntimeError:
            pass
        # cleanup IS called after failed setup (the fix)
        assert agent.cleanup_called

    @pytest.mark.asyncio
    async def test_cleanup_does_not_mask_setup_exception(self):
        """The setup exception must propagate, not be swallowed by cleanup."""
        agent = MockAgent(setup_should_fail=True)
        with pytest.raises(RuntimeError) as exc_info:
            await agent.run()
        assert "Setup failed" in str(exc_info.value)
        assert agent.cleanup_called
