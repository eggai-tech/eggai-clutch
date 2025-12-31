import pytest

from eggai_clutch import Clutch, Strategy
from eggai_clutch.exceptions import Handover, Terminate


class TestRoundRobinBasic:
    @pytest.mark.asyncio
    async def test_cycles_through_agents(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.ROUND_ROBIN, max_turns=6)

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            return data

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            return data

        await clutch.run("input")
        assert order == ["a", "b", "a", "b", "a", "b"]

    @pytest.mark.asyncio
    async def test_single_agent_repeats(self):
        count = 0
        clutch = Clutch("test", strategy=Strategy.ROUND_ROBIN, max_turns=3)

        @clutch.agent()
        async def agent_a(data):
            nonlocal count
            count += 1
            return data

        await clutch.run("input")
        assert count == 3


class TestRoundRobinTerminate:
    @pytest.mark.asyncio
    async def test_terminate_stops_cycling(self):
        count = 0
        clutch = Clutch("test", strategy=Strategy.ROUND_ROBIN, max_turns=100)

        @clutch.agent()
        async def agent_a(data):
            nonlocal count
            count += 1
            if count >= 3:
                raise Terminate("done")
            return data

        result = await clutch.run("input")
        assert count == 3
        assert result == "done"


class TestRoundRobinHandover:
    @pytest.mark.asyncio
    async def test_handover_redirects(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.ROUND_ROBIN, max_turns=4)

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            if len(order) == 1:
                raise Handover("agent_c")
            raise Terminate()

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            return data

        @clutch.agent()
        async def agent_c(data):
            order.append("c")
            return data

        await clutch.run("input")
        # a -> handover to c (idx=2) -> c runs (idx=3) -> 3%3=0 -> a (terminate)
        assert order == ["a", "c", "a"]
