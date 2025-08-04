# test_module.py – Beispieltest für Paw Control
def test_dummy():
    assert 1 + 1 == 2

def test_config_fixture(basic_config):
    assert basic_config["dummy"] is True
