from visor_video.visor_video import _canales_no_admitidos, FILTROS, TODOS


def test_filtro_limitado_a_dos_tubos():
    assert list(FILTROS) == [TODOS, "Tubo 1", "Tubo 2"]
    assert FILTROS[TODOS] is None
    assert FILTROS["Tubo 1"] == "1"
    assert FILTROS["Tubo 2"] == "2"


def test_archivos_de_un_o_dos_tubos_son_admitidos():
    assert _canales_no_admitidos(["1"]) == []
    assert _canales_no_admitidos(["1", "2"]) == []


def test_tercer_tubo_se_rechaza_explicita_y_completamente():
    assert _canales_no_admitidos(["1", "2", "3"]) == ["3"]
    assert _canales_no_admitidos(["1", "2", "10"]) == ["10"]
