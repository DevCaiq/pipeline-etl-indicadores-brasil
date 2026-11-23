import json

import pytest

from pipeline_etl.api.cache import CacheLeitura, ErroBackendCache, criar_chave_cache

RESPOSTA = b'{"data":[],"meta":{}}'


class RedisFalso:
    def __init__(self):
        self.dados = {}
        self.chamadas = 0
        self.falha = False
        self.validades = []
        self.liberacoes = []

    def get(self, name):
        self.chamadas += 1
        if self.falha:
            raise ErroBackendCache("indisponivel")
        return self.dados.get(name)

    def set(self, name, value, *, ex=None, px=None, nx=False):
        if self.falha:
            raise ErroBackendCache("indisponivel")
        if nx and name in self.dados:
            return False
        self.dados[name] = value
        self.validades.append((ex, px))
        return True

    def eval(self, script, numkeys, *keys_and_args):
        chave, token = keys_and_args
        self.liberacoes.append((script, numkeys, chave, token))
        if self.dados.get(chave) == token:
            del self.dados[chave]
            return 1
        return 0


def test_chave_isola_geracao_estado_cursor_e_limite():
    argumentos = dict(
        dominio="bcb",
        camada="gold",
        versao=1,
        data_publicacao={"pendente": False},
        rota="/series",
        parametros={"cursor": "segredo", "limite": 10},
    )
    chave = criar_chave_cache(**argumentos)
    assert "segredo" not in chave
    assert chave == criar_chave_cache(
        **{**argumentos, "parametros": {"limite": 10, "cursor": "segredo"}}
    )
    for campo, valor in [
        ("versao", 2),
        ("data_publicacao", {"pendente": True}),
        ("parametros", {"cursor": "outro", "limite": 10}),
        ("parametros", {"cursor": "segredo", "limite": 20}),
    ]:
        assert chave != criar_chave_cache(**{**argumentos, campo: valor})


def test_ausencia_hit_validade_e_liberacao():
    redis = RedisFalso()
    cache = CacheLeitura(redis)
    assert cache.obter_ou_calcular("chave", lambda: RESPOSTA) == RESPOSTA
    assert cache.obter_ou_calcular("chave", lambda: pytest.fail("hit esperado")) == RESPOSTA
    assert any(ex is not None and 270 <= ex <= 330 for ex, px in redis.validades)
    assert "chave:trava" not in redis.dados
    assert redis.liberacoes[0][1] == 1


def test_circuito_impede_rede_ate_cinco_segundos():
    instante = [0.0]
    redis = RedisFalso()
    redis.falha = True
    cache = CacheLeitura(redis, relogio=lambda: instante[0])
    assert cache.obter_ou_calcular("a", lambda: RESPOSTA) == RESPOSTA
    redis.falha = False
    instante[0] = 4.9
    assert cache.obter_ou_calcular("a", lambda: RESPOSTA) == RESPOSTA
    assert redis.chamadas == 1
    instante[0] = 5.0
    cache.obter_ou_calcular("a", lambda: RESPOSTA)
    assert redis.chamadas > 1


@pytest.mark.parametrize(
    "conteudo", [b"erro", b"[]", b"{}", b'{"data":[]}', b"x" * (2 * 1024 * 1024 + 1)]
)
def test_conteudo_corrompido_nao_e_hit(conteudo):
    redis = RedisFalso()
    redis.dados["a"] = conteudo
    assert CacheLeitura(redis).obter_ou_calcular("a", lambda: RESPOSTA) == RESPOSTA


def test_sem_cliente_e_erro_aplicacao_nao_sao_mascarados():
    assert CacheLeitura(None).obter_ou_calcular("a", lambda: RESPOSTA) == RESPOSTA

    def falhar():
        raise ValueError("erro da consulta")

    with pytest.raises(ValueError, match="consulta"):
        CacheLeitura(RedisFalso()).obter_ou_calcular("a", falhar)


def test_concorrente_reaproveita_resultado_publicado_na_espera():
    redis = RedisFalso()
    redis.dados["a:trava"] = "outro"

    def esperar(duracao):
        assert 0 <= duracao <= 0.1
        redis.dados["a"] = RESPOSTA

    cache = CacheLeitura(redis, esperar=esperar)
    assert cache.obter_ou_calcular("a", lambda: pytest.fail("coalescer")) == RESPOSTA


def test_contencao_nao_publica_sem_posse():
    redis = RedisFalso()
    redis.dados["a:trava"] = "outro"
    cache = CacheLeitura(redis, esperar=lambda _: None)
    assert cache.obter_ou_calcular("a", lambda: RESPOSTA) == RESPOSTA
    assert "a" not in redis.dados
    assert redis.dados["a:trava"] == "outro"


def test_liberacao_nao_remove_trava_renovada():
    redis = RedisFalso()

    def calcular():
        redis.dados["a:trava"] = "novo"
        return RESPOSTA

    CacheLeitura(redis).obter_ou_calcular("a", calcular)
    assert redis.dados["a:trava"] == "novo"


def test_falha_escrita_preserva_resposta_calculada():
    redis = RedisFalso()

    def calcular():
        redis.falha = True
        return RESPOSTA

    assert CacheLeitura(redis).obter_ou_calcular("a", calcular) == RESPOSTA


def test_resposta_calculada_invalida_nao_e_armazenada():
    redis = RedisFalso()
    resposta = json.dumps({"erro": "aplicacao"}).encode()
    assert CacheLeitura(redis).obter_ou_calcular("a", lambda: resposta) == resposta
    assert "a" not in redis.dados


def test_duas_consultas_concorrentes_calculam_uma_vez():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    redis = RedisFalso()
    calculando = threading.Event()
    permitir = threading.Event()
    chamadas = []

    def calcular():
        chamadas.append(True)
        calculando.set()
        assert permitir.wait(timeout=2)
        return RESPOSTA

    def esperar(duracao):
        permitir.set()
        assert concluido.wait(timeout=2)

    concluido = threading.Event()
    cache = CacheLeitura(redis, esperar=esperar)

    def primeira_consulta():
        try:
            return cache.obter_ou_calcular("a", calcular)
        finally:
            concluido.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        primeira = executor.submit(primeira_consulta)
        assert calculando.wait(timeout=2)
        segunda = executor.submit(cache.obter_ou_calcular, "a", calcular)
        assert primeira.result(timeout=2) == RESPOSTA
        assert segunda.result(timeout=2) == RESPOSTA
    assert len(chamadas) == 1


def test_erro_operacional_da_consulta_nao_abre_circuito():
    redis = RedisFalso()
    cache = CacheLeitura(redis)

    def falhar():
        raise TimeoutError("banco")

    with pytest.raises(TimeoutError, match="banco"):
        cache.obter_ou_calcular("a", falhar)
    cache.obter_ou_calcular("a", lambda: RESPOSTA)
    assert redis.dados["a"] == RESPOSTA


def test_metricas_cache_distinguem_acerto_calculo_falha_e_circuito():
    from pipeline_etl.api.metricas import MetricasAPI

    metricas = MetricasAPI()
    redis = RedisFalso()
    cache = CacheLeitura(redis, observar=metricas.observar_cache)
    assert cache.obter_ou_calcular("segredo", lambda: RESPOSTA) == RESPOSTA
    assert (
        cache.obter_ou_calcular("segredo", lambda: pytest.fail("Acerto não calcula.")) == RESPOSTA
    )
    redis.falha = True
    assert cache.obter_ou_calcular("outra", lambda: RESPOSTA) == RESPOSTA
    assert cache.obter_ou_calcular("mais", lambda: RESPOSTA) == RESPOSTA
    metricas.observar_cache("rotulo_privado")
    conteudo = metricas.gerar().decode()
    assert 'cache_eventos_total{evento="acerto"} 1.0' in conteudo
    assert 'cache_eventos_total{evento="calculo"} 3.0' in conteudo
    assert 'cache_eventos_total{evento="falha_backend"} 1.0' in conteudo
    assert 'cache_eventos_total{evento="circuito_aberto"} 1.0' in conteudo
    assert "segredo" not in conteudo and "rotulo_privado" not in conteudo


def test_observador_falho_nao_interrompe_cache_nem_expoe_erro(caplog):
    def falhar(evento):
        raise RuntimeError("senha=segredo")

    cache = CacheLeitura(None, observar=falhar)
    assert cache.obter_ou_calcular("a", lambda: RESPOSTA) == RESPOSTA
    assert "segredo" not in caplog.text
