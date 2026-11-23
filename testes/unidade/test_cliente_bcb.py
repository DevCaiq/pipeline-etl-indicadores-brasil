"""HTTP real sobre MockTransport; nenhuma chamada externa."""

import gzip
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.erros import ColetaAdiada, ErroColeta


class RelogioSimulado:
    """Avança sem aguardar tempo real nos cenários de retentativa."""

    def __init__(self) -> None:
        self.segundos = 0.0
        self.esperas: list[float] = []

    def ler(self) -> float:
        return self.segundos

    def aguardar(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.segundos += segundos

    def agora(self) -> datetime:
        return datetime(2026, 11, 18, tzinfo=UTC) + timedelta(seconds=self.segundos)


def resposta_http(
    status: int = 200, corpo: bytes = b"[]", cabecalhos: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status, stream=httpx.ByteStream(corpo), headers=cabecalhos)


def montar_cliente(
    transporte: httpx.Client, relogio: RelogioSimulado, **opcoes: float
) -> ClienteBCB:
    return ClienteBCB(
        transporte, dormir=relogio.aguardar, relogio=relogio.ler, agora=relogio.agora, **opcoes
    )


def test_preserva_bytes_e_nao_interpreta_json() -> None:
    corpo = b"isto nao e json"
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: resposta_http(corpo=corpo))
    ) as transporte:
        resposta = montar_cliente(transporte, RelogioSimulado()).buscar(
            432, date(2020, 1, 2), date(2020, 1, 6)
        )
    assert resposta.corpo == corpo
    assert resposta.parametros["dataInicial"] == "02/01/2020"
    assert resposta.status_http == 200


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retenta_falha_transitoria_ate_sucesso(status: int) -> None:
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return resposta_http(status if len(chamadas) == 1 else 200)

    relogio = RelogioSimulado()
    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        montar_cliente(transporte, relogio).buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert len(chamadas) == 2
    assert 1 <= sum(relogio.esperas) <= 2


@pytest.mark.parametrize("status", [400, 404, 501, 302])
def test_nao_retenta_erro_permanente_ou_redirect(status: int) -> None:
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return resposta_http(status, cabecalhos={"Location": "https://outro.exemplo"})

    with (
        httpx.Client(transport=httpx.MockTransport(responder), follow_redirects=True) as transporte,
        pytest.raises(ErroColeta),
    ):
        montar_cliente(transporte, RelogioSimulado()).buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert len(chamadas) == 1


def test_esgota_cinco_tentativas_em_timeout() -> None:
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        raise httpx.ReadTimeout("Tempo esgotado", request=requisicao)

    with (
        httpx.Client(transport=httpx.MockTransport(responder)) as transporte,
        pytest.raises(ErroColeta),
    ):
        montar_cliente(transporte, RelogioSimulado()).buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert len(chamadas) == 5


@pytest.mark.parametrize("usar_data", [False, True])
def test_respeita_retry_after_segundos_e_data(usar_data: bool) -> None:
    relogio = RelogioSimulado()
    cabecalho = (
        format_datetime(relogio.agora() + timedelta(seconds=10), usegmt=True) if usar_data else "10"
    )
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return (
            resposta_http(429, cabecalhos={"Retry-After": cabecalho})
            if len(chamadas) == 1
            else resposta_http()
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        montar_cliente(transporte, relogio).buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert sum(relogio.esperas) == 10


def test_adia_em_vez_de_reduzir_retry_after() -> None:
    relogio = RelogioSimulado()
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: resposta_http(429, cabecalhos={"Retry-After": "3600"})
            )
        ) as transporte,
        pytest.raises(ColetaAdiada) as erro,
    ):
        montar_cliente(transporte, relogio).buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert erro.value.proxima_tentativa_em == relogio.agora() + timedelta(hours=1)
    assert relogio.esperas == []


def test_intervalo_minimo_entre_consultas() -> None:
    relogio = RelogioSimulado()
    with httpx.Client(transport=httpx.MockTransport(lambda _: resposta_http())) as transporte:
        cliente = montar_cliente(transporte, relogio)
        for _ in range(2):
            cliente.buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert relogio.esperas == [1.0]


def test_gzip_e_preservado_antes_de_descompressao() -> None:
    corpo = gzip.compress(b'[{"data":"02/01/2020","valor":"4.50"}]')
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: resposta_http(corpo=corpo, cabecalhos={"Content-Encoding": "gzip"})
        )
    ) as transporte:
        resposta = montar_cliente(transporte, RelogioSimulado()).buscar(
            432, date(2020, 1, 2), date(2020, 1, 6)
        )
    assert resposta.corpo == corpo
    assert resposta.codificacao_conteudo == "gzip"


def test_rejeita_corpo_acima_do_limite() -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: resposta_http(corpo=b"12345"))
        ) as transporte,
        pytest.raises(ErroColeta, match="limite"),
    ):
        ClienteBCB(transporte, limite_bytes=4).buscar(1, date(2020, 1, 2), date(2020, 1, 6))


def test_nao_aceita_resposta_apos_orcamento() -> None:
    relogio = RelogioSimulado()

    def responder(requisicao: httpx.Request) -> httpx.Response:
        relogio.segundos = 181
        return resposta_http()

    with (
        httpx.Client(transport=httpx.MockTransport(responder)) as transporte,
        pytest.raises(ErroColeta, match="orçamento"),
    ):
        montar_cliente(transporte, relogio).buscar(1, date(2020, 1, 2), date(2020, 1, 6))


@pytest.mark.parametrize(
    "codigo,inicio,fim",
    [
        (999, date(2020, 1, 1), date(2020, 1, 2)),
        (1, date(2020, 1, 2), date(2020, 1, 1)),
        (1, date(2020, 1, 1), date(2021, 1, 1)),
    ],
)
def test_rejeita_parametros_antes_da_rede(codigo: int, inicio: date, fim: date) -> None:

    def responder(requisicao: httpx.Request) -> httpx.Response:
        pytest.fail("Não deveria consultar a rede.")

    with (
        httpx.Client(transport=httpx.MockTransport(responder)) as transporte,
        pytest.raises(ValueError),
    ):
        ClienteBCB(transporte).buscar(codigo, inicio, fim)


def test_adiamento_bloqueia_outra_serie_no_mesmo_cliente() -> None:
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return (
            resposta_http(429, cabecalhos={"Retry-After": "3600"})
            if len(chamadas) == 1
            else resposta_http()
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        cliente = montar_cliente(transporte, RelogioSimulado())
        with pytest.raises(ColetaAdiada):
            cliente.buscar(1, date(2020, 1, 2), date(2020, 1, 6))
        with pytest.raises(ColetaAdiada):
            cliente.buscar(432, date(2020, 1, 2), date(2020, 1, 6))
    assert len(chamadas) == 1


@pytest.mark.parametrize("valor", ["invalido", "-10", "Wed, 01 Jan 2020 00:00:00 GMT"])
def test_retry_after_invalido_ou_passado_usa_backoff(valor: str) -> None:
    relogio = RelogioSimulado()
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return (
            resposta_http(503, cabecalhos={"Retry-After": valor})
            if len(chamadas) == 1
            else resposta_http()
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        montar_cliente(transporte, relogio).buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert len(chamadas) == 2
    assert 1 <= sum(relogio.esperas) <= 2


def test_recupera_falha_de_conexao() -> None:
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        if len(chamadas) == 1:
            raise httpx.ConnectError("Falha simulada", request=requisicao)
        return resposta_http()

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        montar_cliente(transporte, RelogioSimulado()).buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert len(chamadas) == 2


@pytest.mark.parametrize("orcamento", [0, -1, float("nan"), float("inf")])
def test_rejeita_orcamento_invalido(orcamento: float) -> None:
    with httpx.Client() as transporte, pytest.raises(ValueError):
        ClienteBCB(transporte, orcamento_segundos=orcamento)


def test_retry_after_extremo_nao_causa_retentativa_antecipada() -> None:
    relogio = RelogioSimulado()
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return resposta_http(429, cabecalhos={"Retry-After": "9" * 500})

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        cliente = montar_cliente(transporte, relogio)
        for codigo in (1, 432):
            with pytest.raises(ColetaAdiada):
                cliente.buscar(codigo, date(2020, 1, 2), date(2020, 1, 6))
    assert len(chamadas) == 1
    assert relogio.esperas == []


def test_contabiliza_rede_e_retentativas_sem_contar_espera_adiada():
    chamadas = []

    def responder(requisicao):
        chamadas.append(requisicao)
        return resposta_http(503, cabecalhos={"Retry-After": "999"})

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        cliente = montar_cliente(transporte, RelogioSimulado())
        with pytest.raises(ColetaAdiada):
            cliente.buscar(1, date(2020, 1, 2), date(2020, 1, 6))
    assert cliente.metricas_coleta == {"requisicoes": 1, "retentativas": 0}


def test_contabiliza_timeout_sem_resposta_e_separa_consultas():
    chamadas = []

    def responder(requisicao):
        chamadas.append(requisicao)
        if len(chamadas) == 1:
            raise httpx.ReadTimeout("tempo esgotado")
        return resposta_http()

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        cliente = montar_cliente(transporte, RelogioSimulado())
        cliente.buscar(1, date(2020, 1, 2), date(2020, 1, 6))
        cliente.buscar(432, date(2020, 1, 2), date(2020, 1, 6))
    assert cliente.metricas_coleta == {"requisicoes": 3, "retentativas": 1}
