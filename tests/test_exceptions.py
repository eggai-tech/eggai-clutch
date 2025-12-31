from eggai_clutch.exceptions import Handover, Terminate


class TestTerminate:
    def test_terminate_without_result(self):
        exc = Terminate()
        assert exc.result is None

    def test_terminate_with_result(self):
        exc = Terminate("final_value")
        assert exc.result == "final_value"

    def test_terminate_with_dict_result(self):
        result = {"key": "value", "count": 42}
        exc = Terminate(result)
        assert exc.result == result

    def test_terminate_is_exception(self):
        assert issubclass(Terminate, Exception)


class TestHandover:
    def test_handover_without_data(self):
        exc = Handover("next_agent")
        assert exc.agent == "next_agent"
        assert exc.data is None

    def test_handover_with_data(self):
        exc = Handover("next_agent", {"payload": "data"})
        assert exc.agent == "next_agent"
        assert exc.data == {"payload": "data"}

    def test_handover_is_exception(self):
        assert issubclass(Handover, Exception)
