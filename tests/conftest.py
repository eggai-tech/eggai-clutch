import pytest

from eggai_clutch import Clutch, Strategy


@pytest.fixture
def make_clutch():
    def factory(name="test", strategy=Strategy.SEQUENTIAL, **kwargs):
        return Clutch(name, strategy=strategy, **kwargs)

    return factory
