import pytest
from pydantic import BaseModel

from eggai_clutch import Clutch, Strategy
from eggai_clutch.exceptions import Terminate
from eggai_clutch.message import get_context


class TestPipeline:
    @pytest.mark.asyncio
    async def test_three_stage_pipeline(self):
        clutch = Clutch("pipeline")

        @clutch.agent()
        async def validate(data):
            return {"validated": True, **data}

        @clutch.agent()
        async def enrich(data):
            return {"enriched": True, **data}

        @clutch.agent()
        async def format_output(data):
            return {"formatted": True, **data}

        result = await clutch.run({"user": "test"})
        assert result == {
            "user": "test",
            "validated": True,
            "enriched": True,
            "formatted": True,
        }


class TestLoopWithTermination:
    @pytest.mark.asyncio
    async def test_accumulator_loop(self):
        clutch = Clutch("loop", strategy=Strategy.ROUND_ROBIN, max_turns=100)

        @clutch.agent()
        async def accumulator(data):
            value = data.get("value", 0) + 1
            if value >= 5:
                raise Terminate({"final": value})
            return {"value": value}

        result = await clutch.run({})
        assert result == {"final": 5}


class TestDynamicRouting:
    @pytest.mark.asyncio
    async def test_conditional_routing(self):
        clutch = Clutch("router", strategy=Strategy.SELECTOR)

        @clutch.selector
        async def route(data):
            if data.get("type") == "quick":
                return "fast_handler"
            elif data.get("type") == "complex":
                return "slow_handler"
            return None

        @clutch.agent()
        async def fast_handler(data):
            return {"result": "fast", **data}

        @clutch.agent()
        async def slow_handler(data):
            return {"result": "slow", **data}

        fast_result = await clutch.run({"type": "quick"})
        assert fast_result["result"] == "fast"

        slow_result = await clutch.run({"type": "complex"})
        assert slow_result["result"] == "slow"


class TestHistoryAccumulation:
    @pytest.mark.asyncio
    async def test_history_tracks_steps(self):
        clutch = Clutch("history_test")
        captured_ctx = None

        @clutch.agent()
        async def agent_a(data):
            return "from_a"

        @clutch.agent()
        async def agent_b(data):
            nonlocal captured_ctx
            captured_ctx = get_context()
            return "from_b"

        await clutch.run("input")

        assert captured_ctx is not None
        history = captured_ctx.state.history
        # History contains the previous step's source (input -> agent_a's context)
        assert len(history) == 1
        assert history[0]["source"] == "input"
        assert history[0]["data"] == "input"


class TestPydanticFlow:
    @pytest.mark.asyncio
    async def test_pydantic_input_conversion(self):
        class Request(BaseModel):
            query: str
            limit: int = 10

        class Response(BaseModel):
            results: list[str]

        clutch = Clutch("pydantic_test")

        @clutch.agent()
        async def search(req: Request) -> Response:
            return Response(results=[req.query] * req.limit)

        result = await clutch.run({"query": "test", "limit": 3})
        assert result == {"results": ["test", "test", "test"]}

    @pytest.mark.asyncio
    async def test_pydantic_serialization(self):
        class Item(BaseModel):
            name: str
            price: float

        clutch = Clutch("serialize_test")

        @clutch.agent()
        async def create_item(data):
            return Item(name="Widget", price=9.99)

        @clutch.agent()
        async def process_item(data):
            # Should receive serialized dict
            return {"processed": data["name"], "cost": data["price"]}

        result = await clutch.run({})
        assert result == {"processed": "Widget", "cost": 9.99}


class TestGraphWorkflow:
    @pytest.mark.asyncio
    async def test_branching_workflow(self):
        clutch = Clutch("workflow", strategy=Strategy.GRAPH)

        @clutch.agent(edges=["validator"])
        async def intake(data):
            return {"intake": True, **data}

        @clutch.agent(edges=["processor"])
        async def validator(data):
            if not data.get("valid", True):
                raise Terminate({"error": "invalid"})
            return {"validated": True, **data}

        @clutch.agent()
        async def processor(data):
            return {"processed": True, **data}

        result = await clutch.run({"item": "test"})
        assert result["intake"] is True
        assert result["validated"] is True
        assert result["processed"] is True

        invalid_result = await clutch.run({"item": "bad", "valid": False})
        assert invalid_result == {"error": "invalid"}


class TestContextAccess:
    @pytest.mark.asyncio
    async def test_context_accessible_in_agent(self):
        clutch = Clutch("context_test")
        captured_data = None

        @clutch.agent()
        async def inspector(data):
            nonlocal captured_data
            ctx = get_context()
            captured_data = {
                "clutch_id": ctx.state.clutch_id,
                "turn": ctx.state.turn,
                "source": ctx.source,
            }
            return data

        await clutch.run("test")

        assert captured_data is not None
        assert captured_data["turn"] == 0
        assert captured_data["source"] == "input"

    @pytest.mark.asyncio
    async def test_context_cleared_after_run(self):
        clutch = Clutch("cleanup_test")

        @clutch.agent()
        async def agent(data):
            return data

        await clutch.run("test")

        with pytest.raises(RuntimeError):
            get_context()


class TestMaxTurnsBehavior:
    @pytest.mark.asyncio
    async def test_max_turns_prevents_infinite_loop(self):
        count = 0
        clutch = Clutch("loop", strategy=Strategy.SELECTOR, max_turns=5)

        @clutch.selector
        async def always_a(data):
            return "agent_a"

        @clutch.agent()
        async def agent_a(data):
            nonlocal count
            count += 1
            return data

        await clutch.run("input")
        assert count == 5
