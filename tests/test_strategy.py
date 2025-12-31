from eggai_clutch.strategy import Strategy


class TestStrategy:
    def test_sequential_value(self):
        assert Strategy.SEQUENTIAL.value == "sequential"

    def test_round_robin_value(self):
        assert Strategy.ROUND_ROBIN.value == "round_robin"

    def test_graph_value(self):
        assert Strategy.GRAPH.value == "graph"

    def test_selector_value(self):
        assert Strategy.SELECTOR.value == "selector"

    def test_all_strategies_exist(self):
        strategies = [s for s in Strategy]
        assert len(strategies) == 4
