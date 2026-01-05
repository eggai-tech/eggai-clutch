import asyncio
import uuid

import pytest
from eggai import InMemoryTransport
from eggai.transport import eggai_set_default_transport
from eggai.transport.inmemory import InMemoryTransport as InMemoryTransportClass

from eggai_clutch import Clutch, Strategy
from eggai_clutch.exceptions import Handover, Terminate


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


class TestUnifiedAPI:
    @pytest.mark.asyncio
    async def test_same_code_local_and_distributed(self, transport):
        test_id = uuid.uuid4().hex[:8]

        async def run_pipeline(clutch):
            @clutch.agent()
            async def agent_a(data):
                return data + "_a"

            @clutch.agent()
            async def agent_b(data):
                return data + "_b"

            return await clutch.run("input")

        local = Clutch(f"local-{test_id}")
        local_result = await run_pipeline(local)

        distributed = Clutch(f"dist-{test_id}", transport=transport)
        dist_result = await run_pipeline(distributed)
        await distributed.stop()

        assert local_result == dist_result == "input_a_b"

    @pytest.mark.asyncio
    async def test_context_manager(self, transport):
        test_id = uuid.uuid4().hex[:8]

        async with Clutch(f"ctx-{test_id}", transport=transport) as clutch:

            @clutch.agent()
            async def echo(data):
                return data + "_done"

            result = await clutch.run("test")
            assert result == "test_done"


class TestDistributedSequential:
    @pytest.mark.asyncio
    async def test_sequential_distributed(self, transport):
        test_id = uuid.uuid4().hex[:8]
        clutch = Clutch(f"seq-{test_id}", transport=transport)

        @clutch.agent()
        async def agent_a(data):
            return data + "_a"

        @clutch.agent()
        async def agent_b(data):
            return data + "_b"

        result = await clutch.run("input")
        assert result == "input_a_b"
        await clutch.stop()

    @pytest.mark.asyncio
    async def test_sequential_terminate(self, transport):
        test_id = uuid.uuid4().hex[:8]
        clutch = Clutch(f"seq-term-{test_id}", transport=transport)

        @clutch.agent()
        async def agent_a(data):
            raise Terminate("stopped_early")

        @clutch.agent()
        async def agent_b(data):
            return data + "_b"

        result = await clutch.run("input")
        assert result == "stopped_early"
        await clutch.stop()

    @pytest.mark.asyncio
    async def test_sequential_handover(self, transport):
        test_id = uuid.uuid4().hex[:8]
        clutch = Clutch(f"seq-hand-{test_id}", transport=transport)

        @clutch.agent()
        async def agent_a(data):
            raise Handover("agent_c", "from_a")

        @clutch.agent()
        async def agent_b(data):
            return data + "_b"

        @clutch.agent()
        async def agent_c(data):
            return data + "_c"

        result = await clutch.run("input")
        assert result == "from_a_c"
        await clutch.stop()


class TestDistributedRoundRobin:
    @pytest.mark.asyncio
    async def test_round_robin_distributed(self, transport):
        test_id = uuid.uuid4().hex[:8]
        clutch = Clutch(
            f"rr-{test_id}",
            strategy=Strategy.ROUND_ROBIN,
            transport=transport,
            max_turns=3,
        )

        count = 0

        @clutch.agent()
        async def counter(data):
            nonlocal count
            count += 1
            if count >= 3:
                raise Terminate(f"count={count}")
            return data

        result = await clutch.run("input")
        assert result == "count=3"
        assert count == 3
        await clutch.stop()


class TestDistributedGraph:
    @pytest.mark.asyncio
    async def test_graph_distributed(self, transport):
        test_id = uuid.uuid4().hex[:8]
        clutch = Clutch(f"graph-{test_id}", strategy=Strategy.GRAPH, transport=transport)

        @clutch.agent(edges=["agent_b"])
        async def agent_a(data):
            return data + "_a"

        @clutch.agent(edges=["agent_c"])
        async def agent_b(data):
            return data + "_b"

        @clutch.agent()
        async def agent_c(data):
            return data + "_c"

        result = await clutch.run("input")
        assert result == "input_a_b_c"
        await clutch.stop()


class TestDistributedSelector:
    @pytest.mark.asyncio
    async def test_selector_distributed(self, transport):
        test_id = uuid.uuid4().hex[:8]
        clutch = Clutch(f"sel-{test_id}", strategy=Strategy.SELECTOR, transport=transport)

        @clutch.selector
        async def route(data):
            if data == "input":
                return "agent_a"
            return None

        @clutch.agent()
        async def agent_a(data):
            return "handled"

        result = await clutch.run("input")
        assert result == "handled"
        await clutch.stop()


class TestDistributedHooks:
    @pytest.mark.asyncio
    async def test_on_step_hook(self, transport):
        test_id = uuid.uuid4().hex[:8]
        steps = []

        async def on_step(step_name, input_data, output_data):
            steps.append((step_name, input_data, output_data))

        clutch = Clutch(
            f"hooks-{test_id}",
            transport=transport,
            on_step=on_step,
        )

        @clutch.agent()
        async def agent_a(data):
            return data + "_a"

        await clutch.run("input")
        await asyncio.sleep(0.1)

        assert len(steps) >= 1
        assert ("agent_a", "input", "input_a") in steps
        await clutch.stop()

    @pytest.mark.asyncio
    async def test_on_request_response_hooks(self, transport):
        test_id = uuid.uuid4().hex[:8]
        requests = []
        responses = []

        async def on_request(event):
            requests.append(event)

        async def on_response(req, resp):
            responses.append((req, resp))

        clutch = Clutch(
            f"reqresp-{test_id}",
            transport=transport,
            on_request=on_request,
            on_response=on_response,
        )

        @clutch.agent()
        async def echo(data):
            return data

        await clutch.run("test_input")
        await asyncio.sleep(0.1)

        assert len(requests) == 1
        assert requests[0]["input"] == "test_input"
        assert len(responses) == 1
        await clutch.stop()


class TestDistributedMultipleRequests:
    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self, transport):
        test_id = uuid.uuid4().hex[:8]
        clutch = Clutch(f"multi-{test_id}", transport=transport)

        @clutch.agent()
        async def double(data):
            return data * 2

        results = await asyncio.gather(
            clutch.run(1),
            clutch.run(2),
            clutch.run(3),
        )

        assert sorted(results) == [2, 4, 6]
        await clutch.stop()


class TestDistributedFallbackToLocal:
    @pytest.mark.asyncio
    async def test_run_without_transport_runs_locally(self):
        clutch = Clutch("local-fallback")

        @clutch.agent()
        async def echo(data):
            return data + "_processed"

        result = await clutch.run("input")
        assert result == "input_processed"


class TestDistributedErrorHandling:
    @pytest.mark.asyncio
    async def test_agent_exception_returns_error(self, transport):
        test_id = uuid.uuid4().hex[:8]
        clutch = Clutch(f"err-{test_id}", transport=transport)

        @clutch.agent()
        async def failing_agent(data):
            raise ValueError("intentional error")

        with pytest.raises(Exception) as exc_info:
            await clutch.run("input")

        assert "intentional error" in str(exc_info.value)
        await clutch.stop()
