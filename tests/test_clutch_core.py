import pytest
from pydantic import BaseModel

from eggai_clutch import Clutch, Strategy
from eggai_clutch.clutch import AgentNode


class InputModel(BaseModel):
    query: str


class TestAgentNode:
    def test_creation(self):
        async def handler(data):
            return data

        node = AgentNode("test", handler)
        assert node.name == "test"
        assert node.handler is handler
        assert node.edges == []

    def test_with_edges(self):
        async def handler(data):
            return data

        node = AgentNode("test", handler, edges=["a", "b"])
        assert node.edges == ["a", "b"]

    def test_extracts_input_type(self):
        async def typed_handler(data: InputModel):
            return data

        node = AgentNode("test", typed_handler)
        assert node.input_type is InputModel

    def test_no_type_hint(self):
        async def untyped_handler(data):
            return data

        node = AgentNode("test", untyped_handler)
        assert node.input_type is None


class TestAgentRegistration:
    def test_register_single_agent(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def my_agent(data):
            return data

        assert "my_agent" in clutch._agents
        assert clutch._agent_order == ["my_agent"]

    def test_register_multiple_agents(self):
        clutch = Clutch("test")

        @clutch.agent()
        async def agent_a(data):
            return data

        @clutch.agent()
        async def agent_b(data):
            return data

        assert "agent_a" in clutch._agents
        assert "agent_b" in clutch._agents
        assert clutch._agent_order == ["agent_a", "agent_b"]

    def test_register_with_edges(self):
        clutch = Clutch("test", strategy=Strategy.GRAPH)

        @clutch.agent(edges=["agent_b"])
        async def agent_a(data):
            return data

        assert clutch._agents["agent_a"].edges == ["agent_b"]


class TestSelectorRegistration:
    def test_register_selector_with_parentheses(self):
        clutch = Clutch("test", strategy=Strategy.SELECTOR)

        @clutch.selector()
        async def select(data):
            return "agent_a"

        assert clutch._selector is not None

    def test_register_selector_without_parentheses(self):
        clutch = Clutch("test", strategy=Strategy.SELECTOR)

        @clutch.selector
        async def select(data):
            return "agent_a"

        assert clutch._selector is not None

    def test_selector_extracts_input_type(self):
        clutch = Clutch("test", strategy=Strategy.SELECTOR)

        @clutch.selector
        async def select(data: InputModel):
            return "agent_a"

        assert clutch._selector_input_type is InputModel


class TestToTyped:
    def test_passthrough_when_no_type(self):
        clutch = Clutch("test")
        data = {"key": "value"}
        result = clutch._to_typed(data, None)
        assert result is data

    def test_passthrough_when_already_typed(self):
        clutch = Clutch("test")
        model = InputModel(query="test")
        result = clutch._to_typed(model, InputModel)
        assert result is model

    def test_convert_dict_to_pydantic(self):
        clutch = Clutch("test")
        data = {"query": "test"}
        result = clutch._to_typed(data, InputModel)
        assert isinstance(result, InputModel)
        assert result.query == "test"

    def test_passthrough_non_dict_non_matching(self):
        clutch = Clutch("test")
        data = "string_data"
        result = clutch._to_typed(data, InputModel)
        assert result == "string_data"


class TestHooks:
    @pytest.mark.asyncio
    async def test_on_step_hook(self):
        calls = []

        async def on_step(step_name, input_data, output_data):
            calls.append((step_name, input_data, output_data))

        clutch = Clutch("test", on_step=on_step)

        @clutch.agent()
        async def agent_a(data):
            return data + "_processed"

        await clutch.run("input")
        assert len(calls) == 1
        assert calls[0] == ("agent_a", "input", "input_processed")

    @pytest.mark.asyncio
    async def test_on_request_hook(self):
        # on_request is only called in distributed mode, so we test the attribute
        async def on_request(event):
            pass

        clutch = Clutch("test", on_request=on_request)
        assert clutch._on_request is on_request

    @pytest.mark.asyncio
    async def test_on_response_hook(self):
        # on_response is only called in distributed mode, so we test the attribute
        async def on_response(request, response):
            pass

        clutch = Clutch("test", on_response=on_response)
        assert clutch._on_response is on_response


class TestExplicitOrder:
    @pytest.mark.asyncio
    async def test_explicit_order(self):
        order = []
        clutch = Clutch("test", order=["agent_b", "agent_a"])

        @clutch.agent()
        async def agent_a(data):
            order.append("a")
            return data

        @clutch.agent()
        async def agent_b(data):
            order.append("b")
            return data

        await clutch.run("input")
        assert order == ["b", "a"]
