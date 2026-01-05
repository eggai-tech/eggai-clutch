from typing import Any


class Terminate(Exception):
    """Raise to stop pipeline execution.

    Optionally pass a result to be returned:
        raise Terminate(my_result)
    """

    def __init__(self, result: Any = None):
        self.result = result
        super().__init__()


class Handover(Exception):
    """Raise to transfer control to another agent.

    Usage:
        raise Handover("other_agent", modified_data)
    """

    def __init__(self, agent: str, data: Any = None):
        self.agent = agent
        self.data = data
        super().__init__()
