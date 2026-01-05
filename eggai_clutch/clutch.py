from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

from pydantic import BaseModel

from .exceptions import Handover, Terminate
from .message import ClutchContext, ClutchState, _serialize, set_context
from .strategy import Strategy

if TYPE_CHECKING:
    from .clutch import Clutch

T = TypeVar("T")


class StepEvent:
    """Event emitted for each pipeline step."""

    __slots__ = ("step", "data", "final")

    def __init__(self, step: str, data: Any, final: bool = False):
        self.step = step
        self.data = data
        self.final = final

    def __repr__(self) -> str:
        return f"StepEvent(step={self.step!r}, final={self.final})"


class ClutchTask:
    """Handle for a submitted task."""

    __slots__ = ("_clutch", "id", "_future", "_event_queue")

    def __init__(
        self,
        clutch: Clutch,
        task_id: str,
        future: asyncio.Future,
        event_queue: asyncio.Queue | None = None,
    ):
        self._clutch = clutch
        self.id = task_id
        self._future = future
        self._event_queue = event_queue

    @property
    def done(self) -> bool:
        """Check if task completed (non-blocking)."""
        return self._future.done()

    def __await__(self):
        """Make task awaitable: `await task`"""
        return self._future.__await__()

    async def result(self, timeout: float = 30.0) -> Any:
        """Wait for result with timeout."""
        return await asyncio.wait_for(asyncio.shield(self._future), timeout=timeout)

    async def stream(self) -> AsyncIterator[StepEvent]:
        """Yield events as each step completes."""
        if self._event_queue is None:
            result = await self._future
            yield StepEvent("_result", result, final=True)
            return

        while True:
            event = await self._event_queue.get()
            yield event
            if event.final:
                break

    def cancel(self) -> None:
        """Cancel the task."""
        self._future.cancel()


class AgentNode:
    def __init__(self, name: str, handler: Callable, edges: list[str] | None = None):
        self.name = name
        self.handler = handler
        self.edges = edges or []
        self.input_type = self._extract_input_type(handler)

    def _extract_input_type(self, handler: Callable) -> type | None:
        try:
            hints = get_type_hints(handler)
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            if params:
                return hints.get(params[0].name)
        except Exception:
            pass
        return None


class Clutch:
    def __init__(
        self,
        name: str,
        strategy: Strategy = Strategy.SEQUENTIAL,
        max_turns: int = 100,
        transport=None,
        order: list[str] | None = None,
        on_request: Callable[[dict], Awaitable[None]] | None = None,
        on_response: Callable[[dict, dict], Awaitable[None]] | None = None,
        on_step: Callable[[str, dict, dict], Awaitable[None]] | None = None,
        broadcast_channel: str | None = None,
        monitor_channel: str | None = None,
    ):
        self.name = name
        self.strategy = strategy
        self.max_turns = max_turns
        self.transport = transport
        self._agents: dict[str, AgentNode] = {}
        self._agent_order: list[str] = []
        self._explicit_order: list[str] | None = order
        self._selector: Callable | None = None
        self._selector_input_type: type | None = None

        self._on_request = on_request
        self._on_response = on_response
        self._on_step = on_step

        self._broadcast_channel_name = broadcast_channel
        self._monitor_channel_name = monitor_channel
        self._monitor_channel = None

        self._started = False
        self._start_lock: asyncio.Lock | None = None
        self._eggai_agent = None
        self._broadcast_channel = None
        self._step_channels: dict[str, Any] = {}
        self._entry_channel = None
        self._replies_channel = None

        self._client_id = uuid.uuid4().hex[:8]
        self._reply_channel_name = f"clutch-{self.name}-replies"
        self._reply_agent = None
        self._reply_transport = None
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._reply_started = False
        self._reply_lock: asyncio.Lock | None = None

    def agent(self, edges: list[str] | None = None):
        def decorator(fn: Callable[[T], Awaitable[Any]]):
            name = fn.__name__
            self._agents[name] = AgentNode(name, fn, edges)
            self._agent_order.append(name)
            return fn

        return decorator

    def selector(self, fn: Callable[[Any], Awaitable[str | None]] | None = None):
        def decorator(f: Callable[[Any], Awaitable[str | None]]):
            self._selector = f
            self._selector_input_type = self._extract_input_type(f)
            return f

        if fn is not None:
            return decorator(fn)
        return decorator

    def _extract_input_type(self, handler: Callable) -> type | None:
        try:
            hints = get_type_hints(handler)
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            if params:
                return hints.get(params[0].name)
        except Exception:
            pass
        return None

    def _get_order(self) -> list[str]:
        if self._explicit_order:
            return self._explicit_order
        return self._agent_order

    # -------------------------------------------------------------------------
    # Unified API
    # -------------------------------------------------------------------------

    async def submit(self, input_data: Any) -> ClutchTask:
        """Submit work, return task handle immediately."""
        if not self.transport:
            return await self._submit_local(input_data)
        await self._ensure_started()
        return await self._submit_distributed(input_data)

    async def run(self, input_data: Any, timeout: float = 30.0) -> Any:
        """Submit and wait. Sugar for common case."""
        task = await self.submit(input_data)
        return await task.result(timeout=timeout)

    async def stream(self, input_data: Any) -> AsyncIterator[StepEvent]:
        """Submit and stream results step by step."""
        task = await self.submit(input_data)
        async for event in task.stream():
            yield event

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
        return False

    async def _ensure_started(self):
        if self._started:
            return

        if self._start_lock is None:
            self._start_lock = asyncio.Lock()

        async with self._start_lock:
            if self._started:
                return
            await self._start_worker()
            await self._start_reply_listener()
            self._started = True

    # -------------------------------------------------------------------------
    # Local execution
    # -------------------------------------------------------------------------

    async def _submit_local(self, input_data: Any) -> ClutchTask:
        task_id = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def execute():
            try:
                result = await self._run_local(input_data)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

        asyncio.create_task(execute())
        return ClutchTask(self, task_id, future)

    async def _run_local(self, input_data: Any) -> Any:
        order = self._get_order()
        ctx = ClutchContext(
            data=_serialize(input_data),
            source="input",
            state=ClutchState(
                clutch_id=uuid.uuid4().hex,
                strategy=self.strategy.value,
                members=order.copy(),
            ),
        )

        if self.strategy == Strategy.SEQUENTIAL:
            ctx = await self._run_sequential(ctx)
        elif self.strategy == Strategy.ROUND_ROBIN:
            ctx = await self._run_round_robin(ctx)
        elif self.strategy == Strategy.GRAPH:
            ctx = await self._run_graph(ctx)
        elif self.strategy == Strategy.SELECTOR:
            ctx = await self._run_selector(ctx)

        return ctx.data

    def _to_typed(self, data: Any, target_type: type | None) -> Any:
        if target_type is None:
            return data
        if isinstance(data, target_type):
            return data
        if isinstance(data, dict) and issubclass(target_type, BaseModel):
            return target_type(**data)
        return data

    async def _call_handler(self, agent: AgentNode, ctx: ClutchContext) -> Any:
        typed_data = self._to_typed(ctx.data, agent.input_type)
        input_data = ctx.data
        set_context(ctx)
        try:
            result = await agent.handler(typed_data)
            serialized = _serialize(result)
            if self._on_step:
                await self._on_step(agent.name, input_data, serialized)
            return serialized
        finally:
            set_context(None)

    async def _run_sequential(self, ctx: ClutchContext) -> ClutchContext:
        order = self._get_order()
        idx = 0
        while idx < len(order) and ctx.state.turn < self.max_turns:
            agent_name = order[idx]
            agent = self._agents[agent_name]
            try:
                result = await self._call_handler(agent, ctx)
                ctx = ctx.next(agent_name, result)
                idx += 1
            except Terminate as t:
                if t.result is not None:
                    ctx = ctx.next(agent_name, _serialize(t.result))
                break
            except Handover as h:
                if h.data is not None:
                    ctx = ctx.next(agent_name, _serialize(h.data))
                if h.agent in self._agents:
                    idx = order.index(h.agent)
                else:
                    break
        return ctx

    async def _run_round_robin(self, ctx: ClutchContext) -> ClutchContext:
        order = self._get_order()
        idx = 0
        while ctx.state.turn < self.max_turns:
            agent_name = order[idx % len(order)]
            agent = self._agents[agent_name]
            try:
                result = await self._call_handler(agent, ctx)
                ctx = ctx.next(agent_name, result)
                idx += 1
            except Terminate as t:
                if t.result is not None:
                    ctx = ctx.next(agent_name, _serialize(t.result))
                break
            except Handover as h:
                if h.data is not None:
                    ctx = ctx.next(agent_name, _serialize(h.data))
                if h.agent in self._agents:
                    idx = order.index(h.agent)
                else:
                    break
        return ctx

    async def _run_graph(self, ctx: ClutchContext) -> ClutchContext:
        order = self._get_order()
        if not order:
            return ctx
        current = order[0]
        while ctx.state.turn < self.max_turns:
            if current not in self._agents:
                break
            agent = self._agents[current]
            try:
                result = await self._call_handler(agent, ctx)
                ctx = ctx.next(current, result)
            except Terminate as t:
                if t.result is not None:
                    ctx = ctx.next(current, _serialize(t.result))
                break
            except Handover as h:
                if h.data is not None:
                    ctx = ctx.next(current, _serialize(h.data))
                if h.agent in self._agents:
                    current = h.agent
                    continue
                break
            if not agent.edges:
                break
            current = agent.edges[0]
        return ctx

    async def _run_selector(self, ctx: ClutchContext) -> ClutchContext:
        forced_next = None
        while ctx.state.turn < self.max_turns:
            if forced_next:
                next_agent = forced_next
                forced_next = None
            elif self._selector:
                typed_data = self._to_typed(ctx.data, self._selector_input_type)
                set_context(ctx)
                try:
                    next_agent = await self._selector(typed_data)
                finally:
                    set_context(None)
            else:
                next_agent = None

            if not next_agent or next_agent not in self._agents:
                break

            agent = self._agents[next_agent]
            try:
                result = await self._call_handler(agent, ctx)
                ctx = ctx.next(next_agent, result)
            except Terminate as t:
                if t.result is not None:
                    ctx = ctx.next(next_agent, _serialize(t.result))
                break
            except Handover as h:
                if h.data is not None:
                    ctx = ctx.next(next_agent, _serialize(h.data))
                if h.agent in self._agents:
                    forced_next = h.agent
                else:
                    break
        return ctx

    # -------------------------------------------------------------------------
    # Distributed execution
    # -------------------------------------------------------------------------

    async def _submit_distributed(self, input_data: Any) -> ClutchTask:
        from eggai import Channel

        clutch_id = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[clutch_id] = future

        request_channel = Channel(f"clutch-{self.name}", transport=self.transport)
        await request_channel.publish(
            {
                "_clutch_request": True,
                "clutch_id": clutch_id,
                "input": _serialize(input_data),
            }
        )

        return ClutchTask(self, clutch_id, future)

    async def _start_worker(self):
        from eggai import Agent, Channel

        order = self._get_order()

        self._entry_channel = Channel(f"clutch-{self.name}", transport=self.transport)
        await self._entry_channel.ensure_exists()

        for agent_name in order:
            channel = Channel(f"clutch-{self.name}-{agent_name}", transport=self.transport)
            await channel.ensure_exists()
            self._step_channels[agent_name] = channel

        self._replies_channel = Channel(self._reply_channel_name, transport=self.transport)
        await self._replies_channel.ensure_exists()

        if self._broadcast_channel_name:
            self._broadcast_channel = Channel(
                self._broadcast_channel_name, transport=self.transport
            )

        if self._monitor_channel_name:
            self._monitor_channel = Channel(self._monitor_channel_name, transport=self.transport)
            await self._monitor_channel.ensure_exists()

        self._eggai_agent = Agent(f"clutch-{self.name}", transport=self.transport)

        @self._eggai_agent.subscribe(
            channel=self._entry_channel,
            group_id=f"clutch-{self.name}-entry",
            filter_by_message=lambda m: m.get("_clutch_request"),
        )
        async def handle_entry(event: dict[str, Any]):
            await self._handle_entry(event)

        for agent_name, channel in self._step_channels.items():
            self._subscribe_step(agent_name, channel)

        await self._eggai_agent.start()

    async def _start_reply_listener(self):
        from eggai import Agent, Channel

        self._reply_transport = self._create_reply_transport()
        reply_channel = Channel(self._reply_channel_name, transport=self._reply_transport)
        await reply_channel.ensure_exists()

        self._reply_agent = Agent(
            f"clutch-reply-{self.name}-{self._client_id}",
            transport=self._reply_transport,
        )

        @self._reply_agent.subscribe(
            channel=reply_channel,
            group_id=f"clutch-reply-{self.name}-{self._client_id}",
        )
        async def handle_reply(event: dict[str, Any]):
            self._handle_reply(event)

        await self._reply_agent.start()
        await asyncio.sleep(0.1)
        self._reply_started = True

    def _subscribe_step(self, step_name: str, channel):
        async def handle_step(event: dict[str, Any]):
            await self._process_step(step_name, event)

        self._eggai_agent.subscribe(
            channel=channel,
            group_id=f"clutch-{self.name}-{step_name}",
            filter_by_message=lambda m: m.get("_clutch_step"),
        )(handle_step)

    async def _handle_entry(self, event: dict[str, Any]):
        clutch_id = event["clutch_id"]
        input_data = event["input"]

        if self._on_request:
            await self._on_request(event)

        first_step = await self._get_first_step(input_data)
        if not first_step or first_step not in self._step_channels:
            await self._send_response(clutch_id, input_data, input_data)
            return

        order = self._get_order()
        state = {
            "clutch_id": clutch_id,
            "strategy": self.strategy.value,
            "members": order,
            "turn": 0,
            "max_turns": self.max_turns,
            "history": [],
            "step_index": 0,
        }

        await self._step_channels[first_step].publish(
            {
                "_clutch_step": True,
                "clutch_id": clutch_id,
                "data": input_data,
                "state": state,
                "metadata": {},
                "original_input": input_data,
            }
        )

    async def _get_first_step(self, data: Any) -> str | None:
        order = self._get_order()
        if not order:
            return None

        if self.strategy == Strategy.SELECTOR:
            if self._selector:
                typed_data = self._to_typed(data, self._selector_input_type)
                return await self._selector(typed_data)
            return None

        return order[0]

    async def _process_step(self, step_name: str, event: dict[str, Any]):
        clutch_id = event["clutch_id"]
        data = event["data"]
        state = event["state"]
        metadata = event.get("metadata", {})
        original_input = event.get("original_input", data)

        agent = self._agents[step_name]

        ctx = ClutchContext(
            data=data,
            source=step_name,
            state=ClutchState(
                clutch_id=clutch_id,
                strategy=state["strategy"],
                members=state["members"],
                turn=state["turn"],
                history=state.get("history", []),
            ),
            metadata=metadata,
        )

        try:
            result = await self._call_handler(agent, ctx)
            ctx = ctx.next(step_name, result)

            await self._publish_step_event(clutch_id, step_name, data, ctx.data, state)

            state["turn"] = ctx.state.turn
            state["history"] = [
                h.model_dump() if hasattr(h, "model_dump") else h for h in ctx.state.history
            ]
            state["step_index"] = state.get("step_index", 0) + 1

            next_step = await self._get_next_step(step_name, ctx, state)

            if next_step and next_step in self._step_channels:
                await self._step_channels[next_step].publish(
                    {
                        "_clutch_step": True,
                        "clutch_id": clutch_id,
                        "data": ctx.data,
                        "state": state,
                        "metadata": ctx.metadata,
                        "original_input": original_input,
                    }
                )
            else:
                await self._send_response(clutch_id, original_input, ctx.data)

        except Terminate as t:
            result = _serialize(t.result) if t.result is not None else data
            await self._send_response(clutch_id, original_input, result)

        except Handover as h:
            if h.data is not None:
                ctx = ctx.next(step_name, _serialize(h.data))
            state["turn"] = ctx.state.turn
            state["history"] = [
                hh.model_dump() if hasattr(hh, "model_dump") else hh for hh in ctx.state.history
            ]

            if h.agent in self._step_channels:
                await self._step_channels[h.agent].publish(
                    {
                        "_clutch_step": True,
                        "clutch_id": clutch_id,
                        "data": ctx.data,
                        "state": state,
                        "metadata": ctx.metadata,
                        "original_input": original_input,
                    }
                )
            else:
                await self._send_response(clutch_id, original_input, ctx.data)

        except Exception as e:
            await self._replies_channel.publish(
                {
                    "_clutch_response": True,
                    "_clutch_error": True,
                    "clutch_id": clutch_id,
                    "error": str(e),
                }
            )

    async def _get_next_step(
        self, current_step: str, ctx: ClutchContext, state: dict
    ) -> str | None:
        order = self._get_order()

        if ctx.state.turn >= state.get("max_turns", self.max_turns):
            return None

        if self.strategy == Strategy.SEQUENTIAL:
            try:
                idx = order.index(current_step)
                if idx + 1 < len(order):
                    return order[idx + 1]
            except ValueError:
                pass
            return None

        elif self.strategy == Strategy.ROUND_ROBIN:
            step_index = state.get("step_index", 0)
            return order[step_index % len(order)]

        elif self.strategy == Strategy.GRAPH:
            agent = self._agents[current_step]
            if agent.edges:
                return agent.edges[0]
            return None

        elif self.strategy == Strategy.SELECTOR:
            if self._selector:
                typed_data = self._to_typed(ctx.data, self._selector_input_type)
                set_context(ctx)
                try:
                    next_agent = await self._selector(typed_data)
                finally:
                    set_context(None)
                if next_agent and next_agent in self._agents:
                    return next_agent
            return None

        return None

    async def _publish_step_event(
        self, clutch_id: str, step_name: str, input_data: Any, output_data: Any, state: dict
    ):
        import time

        event = {
            "_clutch_monitor": True,
            "clutch_id": clutch_id,
            "step": step_name,
            "turn": state.get("turn", 0),
            "input": input_data,
            "output": output_data,
            "timestamp": time.time(),
        }

        if self._on_step:
            await self._on_step(step_name, input_data, output_data)

        if self._monitor_channel:
            await self._monitor_channel.publish(event)

    async def _send_response(self, clutch_id: str, original_input: Any, result: Any):
        response = {
            "_clutch_response": True,
            "clutch_id": clutch_id,
            "result": result,
        }

        if self._on_response:
            await self._on_response({"clutch_id": clutch_id, "input": original_input}, response)

        if self._broadcast_channel:
            await self._broadcast_channel.publish(
                {
                    "clutch_id": clutch_id,
                    "request": original_input,
                    "result": result,
                }
            )

        await self._replies_channel.publish(response)

    def _handle_reply(self, event: dict[str, Any]):
        if not isinstance(event, dict):
            return
        if not event.get("_clutch_response"):
            return
        clutch_id = event.get("clutch_id")
        if clutch_id not in self._pending_requests:
            return
        future = self._pending_requests.get(clutch_id)
        if future and not future.done():
            if event.get("_clutch_error"):
                future.set_exception(Exception(event.get("error", "Unknown error")))
            else:
                future.set_result(event["result"])

    def _create_reply_transport(self):
        transport_type = type(self.transport).__name__

        if transport_type == "KafkaTransport":
            from eggai import KafkaTransport

            return KafkaTransport(bootstrap_servers=self.transport._bootstrap_servers)
        else:
            return self.transport

    async def stop(self):
        """Stop worker and client agents. Called automatically by context manager."""
        if self._eggai_agent:
            await self._eggai_agent.stop()
            self._eggai_agent = None

        if self._reply_agent:
            await self._reply_agent.stop()
            self._reply_agent = None
            self._reply_started = False

        self._started = False


def handover(agent: str, data: Any = None):
    """Transfer control to another agent with optional data."""
    raise Handover(agent, data)
