from enum import Enum


class Strategy(Enum):
    SEQUENTIAL = "sequential"
    ROUND_ROBIN = "round_robin"
    GRAPH = "graph"
    SELECTOR = "selector"
