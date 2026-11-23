"""Bronze IBGE precede interpretação e preserva tentativas HTTP malsucedidas."""

from pathlib import Path

import httpx

from pipeline_etl.processamento.armazenamento.objetos import SistemaArquivosObjetos
from pipeline_etl.processamento.clientes.ibge import ClienteIBGE, ler_coleta


def test_arquiva_corpo_invalido_antes_de_qualquer_parse(tmp_path: Path):
    armazenamento = SistemaArquivosObjetos(tmp_path)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=httpx.ByteStream(b"nao e json"))
        )
    ) as transporte:
        resultado = ClienteIBGE(transporte, armazenamento, dormir=lambda _: None).coletar("regioes")
    assert resultado.situacao == "COLETADA"
    assert ler_coleta(armazenamento, resultado.manifesto).corpo == b"nao e json"


def test_retry_preserva_resposta_500_e_resposta_final(tmp_path: Path):
    chamadas = []

    def responder(requisicao):
        chamadas.append(requisicao)
        return httpx.Response(500 if len(chamadas) == 1 else 200, stream=httpx.ByteStream(b"[]"))

    armazenamento = SistemaArquivosObjetos(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        resultado = ClienteIBGE(transporte, armazenamento, dormir=lambda _: None).coletar("regioes")
    assert resultado.situacao == "COLETADA" and len(chamadas) == 2
    assert len(list(tmp_path.rglob("*.body"))) == 2
    assert ler_coleta(armazenamento, resultado.manifesto).status_http == 200


def test_404_nao_repete_nem_passa_por_lote_valido(tmp_path: Path):
    chamadas = []

    def responder(requisicao):
        chamadas.append(requisicao)
        return httpx.Response(404, stream=httpx.ByteStream(b"inexistente"))

    armazenamento = SistemaArquivosObjetos(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        resultado = ClienteIBGE(transporte, armazenamento, dormir=lambda _: None).coletar("regioes")
    assert resultado.situacao == "FALHA" and len(chamadas) == 1
    assert next(tmp_path.rglob("*.body")).read_bytes() == b"inexistente"


def test_parametros_e_ano_da_consulta_sao_explicitos(tmp_path: Path):
    def responder(requisicao):
        assert requisicao.url.params["localidades"] == "N6[all]"
        assert "/2025/variaveis/9324" in str(requisicao.url)
        return httpx.Response(200, stream=httpx.ByteStream(b"[]"))

    armazenamento = SistemaArquivosObjetos(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        resultado = ClienteIBGE(transporte, armazenamento, dormir=lambda _: None).coletar(
            "populacao", 2025
        )
    assert ler_coleta(armazenamento, resultado.manifesto).ano == 2025


def test_orcamento_cooperativo_interrompe_stream_e_preserva_corpo_parcial(tmp_path):
    instante = [0.0]

    class FluxoLento(httpx.SyncByteStream):
        def __iter__(self):
            yield b"inicio"
            instante[0] = 91.0
            yield b"atrasado"

    armazenamento = SistemaArquivosObjetos(tmp_path)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=FluxoLento()))
    ) as transporte:
        resultado = ClienteIBGE(
            transporte, armazenamento, dormir=lambda _: None, relogio=lambda: instante[0]
        ).coletar("regioes")
    assert resultado.situacao == "FALHA"
    assert len(list(tmp_path.rglob("*.body"))) == 1
    assert next(tmp_path.rglob("*.body")).read_bytes() == b"inicio"


def test_metricas_contam_falhas_de_rede_sem_exigir_resposta(tmp_path):
    chamadas = []

    def responder(requisicao):
        chamadas.append(requisicao)
        if len(chamadas) < 3:
            raise httpx.ConnectError("falha de rede")
        return httpx.Response(200, stream=httpx.ByteStream(b"[]"))

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        cliente = ClienteIBGE(transporte, SistemaArquivosObjetos(tmp_path), dormir=lambda _: None)
        cliente.coletar("regioes")
        cliente.coletar("ufs")
    assert cliente.metricas_coleta == {"requisicoes": 4, "retentativas": 2}
