import asyncio

import pytest
from eggai import InMemoryTransport
from eggai.transport import eggai_set_default_transport
from eggai.transport.inmemory import InMemoryTransport as InMemoryTransportClass

from eggai_clutch import Clutch, ClutchTask, StepEvent


@pytest.fixture(autouse=True)
def reset_transport():
    InMemoryTransportClass._CHANNELS.clear()
    InMemoryTransportClass._SUBSCRIPTIONS.clear()
    yield
    InMemoryTransportClass._CHANNELS.clear()
    InMemoryTransportClass._SUBSCRIPTIONS.clear()


@pytest.fixture
def transport():
    t = InMemoryTransport()
    eggai_set_default_transport(lambda: InMemoryTransport())
    return t


class TestClutchTaskLocal:
    @pytest.mark.asyncio
    async def test_submit_returns_task(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def echo(data):
            return data + "_done"

        task = await clutch.submit("input")

        assert isinstance(task, ClutchTask)
        assert task.id is not None
        assert not task.done

    @pytest.mark.asyncio
    async def test_await_task(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def echo(data):
            return data + "_done"

        task = await clutch.submit("input")
        result = await task

        assert result == "input_done"
        assert task.done

    @pytest.mark.asyncio
    async def test_task_result_with_timeout(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def echo(data):
            return data + "_done"

        task = await clutch.submit("input")
        result = await task.result(timeout=5.0)

        assert result == "input_done"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tasks(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def double(data):
            return data * 2

        tasks = [await clutch.submit(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert sorted(results) == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_fire_and_forget(self):
        results = []
        clutch = Clutch("test")

        @clutch.agent()
        async def collector(data):
            results.append(data)
            return data

        await clutch.submit("fire")
        await asyncio.sleep(0.1)

        assert results == ["fire"]

    @pytest.mark.asyncio
    async def test_task_cancel(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def slow(data):
            await asyncio.sleep(10)
            return data

        task = await clutch.submit("input")
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_task_exception(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def failing(data):
            raise ValueError("intentional")

        task = await clutch.submit("input")

        with pytest.raises(ValueError, match="intentional"):
            await task

    @pytest.mark.asyncio
    async def test_stream_final_result(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def echo(data):
            return data + "_done"

        events = []
        async for event in clutch.stream("input"):
            events.append(event)

        assert len(events) == 1
        assert events[0].final
        assert events[0].data == "input_done"


class TestClutchTaskDistributed:
    @pytest.mark.asyncio
    async def test_submit_distributed(self, transport):
        clutch = Clutch("dist-test", transport=transport)

        @clutch.agent()
        async def echo(data):
            return data + "_done"

        task = await clutch.submit("input")

        assert isinstance(task, ClutchTask)
        assert task.id is not None

        result = await task.result(timeout=5.0)
        assert result == "input_done"

        await clutch.stop()

    @pytest.mark.asyncio
    async def test_await_distributed_task(self, transport):
        clutch = Clutch("dist-test2", transport=transport)

        @clutch.agent()
        async def double(data):
            return data * 2

        task = await clutch.submit(21)
        result = await task

        assert result == 42
        await clutch.stop()

    @pytest.mark.asyncio
    async def test_multiple_distributed_tasks(self, transport):
        clutch = Clutch("dist-multi", transport=transport)

        @clutch.agent()
        async def triple(data):
            return data * 3

        tasks = [await clutch.submit(i) for i in range(3)]
        results = await asyncio.gather(*[t.result(timeout=5.0) for t in tasks])

        assert sorted(results) == [0, 3, 6]
        await clutch.stop()


class TestStepEvent:
    def test_step_event_creation(self):
        event = StepEvent("agent_a", {"key": "value"}, final=False)

        assert event.step == "agent_a"
        assert event.data == {"key": "value"}
        assert event.final is False

    def test_step_event_final(self):
        event = StepEvent("_result", "final_data", final=True)

        assert event.final is True

    def test_step_event_repr(self):
        event = StepEvent("test", "data", final=True)

        assert "test" in repr(event)
        assert "final=True" in repr(event)
