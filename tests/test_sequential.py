import pytest

from eggai_clutch import Clutch
from eggai_clutch.exceptions import Handover, Terminate


class TestSequentialBasic:
    @pytest.mark.asyncio
    async def test_single_agent(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def agent_a(data):
            return data + "_a"

        result = await clutch.run("input")
        assert result == "input_a"

    @pytest.mark.asyncio
    async def test_multiple_agents_in_order(self):
        order = []
        clutch = Clutch("test")

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            return data + "_a"

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            return data + "_b"

        @clutch.agent()
        async def agent_c(data):
            order.append("c")
            return data + "_c"

        result = await clutch.run("input")
        assert order == ["a", "b", "c"]
        assert result == "input_a_b_c"

    @pytest.mark.asyncio
    async def test_data_flows_between_agents(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def double(data):
            return data * 2

        @clutch.agent()
        async def add_ten(data):
            return data + 10

        result = await clutch.run(5)
        assert result == 20  # (5 * 2) + 10


class TestSequentialTerminate:
    @pytest.mark.asyncio
    async def test_terminate_stops_execution(self):
        executed = []
        clutch = Clutch("test")

        @clutch.agent()
        async def agent_a(data):
            executed.append("a")
            raise Terminate()

        @clutch.agent()
        async def agent_b(data):
            executed.append("b")
            return data

        await clutch.run("input")
        assert executed == ["a"]

    @pytest.mark.asyncio
    async def test_terminate_with_result(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def agent_a(data):
            raise Terminate("final_result")

        @clutch.agent()
        async def agent_b(data):
            return data

        result = await clutch.run("input")
        assert result == "final_result"


class TestSequentialHandover:
    @pytest.mark.asyncio
    async def test_handover_jumps_to_agent(self):
        executed = []
        clutch = Clutch("test")

        @clutch.agent()
        async def agent_a(data):
            executed.append("a")
            raise Handover("agent_c")

        @clutch.agent()
        async def agent_b(data):
            executed.append("b")
            return data

        @clutch.agent()
        async def agent_c(data):
            executed.append("c")
            raise Terminate()

        await clutch.run("input")
        assert executed == ["a", "c"]

    @pytest.mark.asyncio
    async def test_handover_with_data(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def agent_a(data):
            raise Handover("agent_b", "modified_data")

        @clutch.agent()
        async def agent_b(data):
            return data + "_processed"

        result = await clutch.run("input")
        assert result == "modified_data_processed"

    @pytest.mark.asyncio
    async def test_handover_to_nonexistent_stops(self):
        executed = []
        clutch = Clutch("test")

        @clutch.agent()
        async def agent_a(data):
            executed.append("a")
            raise Handover("nonexistent")

        @clutch.agent()
        async def agent_b(data):
            executed.append("b")
            return data

        await clutch.run("input")
        assert executed == ["a"]


class TestSequentialMaxTurns:
    @pytest.mark.asyncio
    async def test_max_turns_limits_execution(self):
        count = 0
        clutch = Clutch("test", max_turns=3)

        @clutch.agent()
        async def agent_a(data):
            nonlocal count
            count += 1
            # Must pass data to increment turn counter
            raise Handover("agent_a", data)

        await clutch.run("input")
        assert count == 3
