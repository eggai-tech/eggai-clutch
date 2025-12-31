import pytest
from pydantic import BaseModel

from eggai_clutch import Clutch, Strategy
from eggai_clutch.exceptions import Handover, Terminate


class TestSelectorBasic:
    @pytest.mark.asyncio
    async def test_routes_to_selected_agent(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.SELECTOR, max_turns=3)

        @clutch.selector
        async def select(data):
            if data == "input":
                return "agent_a"
            elif data == "from_a":
                return "agent_b"
            return None

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            return "from_a"

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            return "from_b"

        result = await clutch.run("input")
        assert order == ["a", "b"]
        assert result == "from_b"

    @pytest.mark.asyncio
    async def test_none_return_stops_execution(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.SELECTOR)

        @clutch.selector
        async def select(data):
            if data == "input":
                return "agent_a"
            return None

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            return "done"

        result = await clutch.run("input")
        assert order == ["a"]
        assert result == "done"

    @pytest.mark.asyncio
    async def test_invalid_agent_stops_execution(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.SELECTOR)

        @clutch.selector
        async def select(data):
            return "nonexistent"

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            return data

        result = await clutch.run("input")
        assert order == []
        assert result == "input"


class TestSelectorNoSelector:
    @pytest.mark.asyncio
    async def test_no_selector_stops_immediately(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.SELECTOR)

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            return data

        result = await clutch.run("input")
        assert order == []
        assert result == "input"


class TestSelectorTyped:
    @pytest.mark.asyncio
    async def test_typed_selector_input(self):
        class Request(BaseModel):
            route: str

        clutch = Clutch("test", strategy=Strategy.SELECTOR)

        @clutch.selector
        async def select(data: Request):
            # Selector is called repeatedly; only route on first call
            if isinstance(data, Request):
                return data.route
            return None

        @clutch.agent()
        async def agent_a(data):
            return "handled_a"

        result = await clutch.run({"route": "agent_a"})
        assert result == "handled_a"


class TestSelectorTerminate:
    @pytest.mark.asyncio
    async def test_terminate_stops_loop(self):
        count = 0
        clutch = Clutch("test", strategy=Strategy.SELECTOR, max_turns=100)

        @clutch.selector
        async def select(data):
            return "agent_a"

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


class TestSelectorHandover:
    @pytest.mark.asyncio
    async def test_handover_forces_next_agent(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.SELECTOR, max_turns=3)

        @clutch.selector
        async def select(data):
            return "agent_a"

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            raise Handover("agent_b")

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            raise Terminate()

        await clutch.run("input")
        assert order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_handover_to_invalid_stops(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.SELECTOR)

        @clutch.selector
        async def select(data):
            return "agent_a"

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            raise Handover("nonexistent")

        await clutch.run("input")
        assert order == ["a"]
