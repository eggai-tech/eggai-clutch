import pytest
from pydantic import BaseModel

from eggai_clutch.message import (
    ClutchContext,
    ClutchState,
    _serialize,
    get_context,
    set_context,
)


class SampleModel(BaseModel):
    name: str
    value: int


class TestClutchState:
    def test_default_values(self):
        state = ClutchState()
        assert state.strategy == "sequential"
        assert state.members == []
        assert state.turn == 0
        assert state.history == []
        assert state.clutch_id is not None

    def test_custom_values(self):
        state = ClutchState(
            clutch_id="test-id",
            strategy="graph",
            members=["a", "b", "c"],
            turn=5,
            history=[{"source": "a", "data": "x"}],
        )
        assert state.clutch_id == "test-id"
        assert state.strategy == "graph"
        assert state.members == ["a", "b", "c"]
        assert state.turn == 5
        assert state.history == [{"source": "a", "data": "x"}]

    def test_serialization(self):
        state = ClutchState(members=["a", "b"])
        dump = state.model_dump()
        assert "clutch_id" in dump
        assert dump["members"] == ["a", "b"]


class TestClutchContext:
    def test_creation(self):
        ctx = ClutchContext(data={"key": "value"}, source="test_agent")
        assert ctx.data == {"key": "value"}
        assert ctx.source == "test_agent"
        assert ctx.state is not None
        assert ctx.metadata == {}

    def test_next_increments_turn(self):
        ctx = ClutchContext(data="input", source="input")
        next_ctx = ctx.next("agent_a", "output")
        assert next_ctx.state.turn == 1
        assert next_ctx.data == "output"
        assert next_ctx.source == "agent_a"

    def test_next_appends_history(self):
        ctx = ClutchContext(data="input", source="input")
        next_ctx = ctx.next("agent_a", "output_a")
        assert len(next_ctx.state.history) == 1
        assert next_ctx.state.history[0]["source"] == "input"
        assert next_ctx.state.history[0]["data"] == "input"

    def test_next_preserves_clutch_id(self):
        ctx = ClutchContext(
            data="input",
            source="input",
            state=ClutchState(clutch_id="fixed-id"),
        )
        next_ctx = ctx.next("agent_a", "output")
        assert next_ctx.state.clutch_id == "fixed-id"

    def test_to_dict(self):
        ctx = ClutchContext(data={"x": 1}, source="src", metadata={"meta": "data"})
        d = ctx.to_dict()
        assert d["data"] == {"x": 1}
        assert d["source"] == "src"
        assert d["metadata"] == {"meta": "data"}
        assert "state" in d

    def test_from_dict(self):
        original = ClutchContext(data={"x": 1}, source="src")
        d = original.to_dict()
        restored = ClutchContext.from_dict(d)
        assert restored.data == original.data
        assert restored.source == original.source


class TestSerialize:
    def test_serialize_dict(self):
        data = {"key": "value"}
        assert _serialize(data) == data

    def test_serialize_pydantic_model(self):
        model = SampleModel(name="test", value=42)
        result = _serialize(model)
        assert result == {"name": "test", "value": 42}

    def test_serialize_primitive(self):
        assert _serialize("hello") == "hello"
        assert _serialize(123) == 123
        assert _serialize(None) is None


class TestContextVar:
    def test_get_context_raises_when_not_set(self):
        set_context(None)
        with pytest.raises(RuntimeError, match="No active Clutch context"):
            get_context()

    def test_set_and_get_context(self):
        ctx = ClutchContext(data="test", source="test")
        set_context(ctx)
        assert get_context() is ctx
        set_context(None)
