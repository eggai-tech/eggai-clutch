import pytest

from eggai_clutch import Clutch, Strategy
from eggai_clutch.exceptions import Handover, Terminate


class TestGraphBasic:
    @pytest.mark.asyncio
    async def test_follows_edges(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.GRAPH)

        @clutch.agent(edges=["agent_b"])
        async def agent_a(data):
            order.append("a")
            return data

        @clutch.agent(edges=["agent_c"])
        async def agent_b(data):
            order.append("b")
            return data

        @clutch.agent()
        async def agent_c(data):
            order.append("c")
            return data

        await clutch.run("input")
        assert order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_stops_when_no_edges(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.GRAPH)

        @clutch.agent(edges=["agent_b"])
        async def agent_a(data):
            order.append("a")
            return data

        @clutch.agent()  # No edges = terminal
        async def agent_b(data):
            order.append("b")
            return data

        @clutch.agent()
        async def agent_c(data):
            order.append("c")
            return data

        await clutch.run("input")
        assert order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_follows_first_edge(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.GRAPH)

        @clutch.agent(edges=["agent_b", "agent_c"])
        async def agent_a(data):
            order.append("a")
            return data

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            return data

        @clutch.agent()
        async def agent_c(data):
            order.append("c")
            return data

        await clutch.run("input")
        assert order == ["a", "b"]


class TestGraphTerminate:
    @pytest.mark.asyncio
    async def test_terminate_stops_traversal(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.GRAPH)

        @clutch.agent(edges=["agent_b"])
        async def agent_a(data):
            order.append("a")
            raise Terminate("early_exit")

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            return data

        result = await clutch.run("input")
        assert order == ["a"]
        assert result == "early_exit"


class TestGraphHandover:
    @pytest.mark.asyncio
    async def test_handover_overrides_edges(self):
        order = []
        clutch = Clutch("test", strategy=Strategy.GRAPH)

        @clutch.agent(edges=["agent_b"])
        async def agent_a(data):
            order.append("a")
            raise Handover("agent_c")

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            return data

        @clutch.agent()
        async def agent_c(data):
            order.append("c")
            return data

        await clutch.run("input")
        assert order == ["a", "c"]

    @pytest.mark.asyncio
    async def test_handover_with_data(self):
        clutch = Clutch("test", strategy=Strategy.GRAPH)

        @clutch.agent(edges=["agent_b"])
        async def agent_a(data):
            raise Handover("agent_b", "new_data")

        @clutch.agent()
        async def agent_b(data):
            return data + "_done"

        result = await clutch.run("input")
        assert result == "new_data_done"


class TestGraphEmpty:
    @pytest.mark.asyncio
    async def test_empty_graph(self):
        clutch = Clutch("test", strategy=Strategy.GRAPH)
        result = await clutch.run("input")
        assert result == "input"
