from importlib.metadata import version

from .clutch import Clutch, ClutchTask, StepEvent, handover
from .exceptions import Handover, Terminate
from .strategy import Strategy

__version__ = version("eggai-clutch")

__all__ = [
    "Clutch",
    "ClutchTask",
    "StepEvent",
    "Strategy",
    "Terminate",
    "Handover",
    "handover",
    "__version__",
]
