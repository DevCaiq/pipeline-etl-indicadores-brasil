"""Coleta IBGE síncrona com bronze por tentativa, antes de interpretar JSON externo."""

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from pipeline_etl.processamento.armazenamento.objetos import ArmazenamentoObjetos, ObjetoBronze
from pipeline_etl.processamento.clientes.bcb import interpretar_espera

LIMITE_CORPO = 8 * 1024 * 1024
RECURSOS = {
    "regioes": "v1/localidades/regioes",
    "ufs": "v1/localidades/estados",
    "municipios": "v1/localidades/municipios",
    "metadados": "v3/agregados/6579/metadados",
    "periodos": "v3/agregados/6579/periodos",
}


def _endereco(recurso: str, ano: int | None) -> tuple[str, dict[str, str]]:
    if recurso == "populacao":
        if type(ano) is not int or not 2020 <= ano <= datetime.now(UTC).year:
            raise ValueError("População exige ano disponível desde 2020.")
        caminho = f"v3/agregados/6579/periodos/{ano}/variaveis/9324"
        parametros = {"localidades": "N6[all]"}
    else:
        if recurso not in RECURSOS or ano is not None:
            raise ValueError("Recurso IBGE inválido.")
        caminho = RECURSOS[recurso]
        parametros = {}
    return "https://servicodados.ibge.gov.br/api/" + caminho, parametros


@dataclass(frozen=True)
class ResultadoColetaIBGE:
    manifesto: ObjetoBronze
    situacao: str


@dataclass(frozen=True)
class ColetaVerificadaIBGE:
    recurso: str
    ano: int | None
    corpo: bytes
    coletado_em: datetime
    status_http: int


class ClienteIBGE:
    def __init__(
        self,
        transporte: httpx.Client,
        armazenamento: ArmazenamentoObjetos,
        *,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transporte = transporte
        self._armazenamento = armazenamento
        self._dormir = dormir
        self._relogio = relogio
        self._ultimo_inicio = float("-inf")
        self._requisicoes = 0
        self._retentativas = 0

    @property
    def metricas_coleta(self) -> dict[str, int]:
        """Devolve cópia dos contadores, incluindo falhas sem resposta HTTP."""
        return {"requisicoes": self._requisicoes, "retentativas": self._retentativas}

    def coletar(self, recurso: str, ano: int | None = None) -> ResultadoColetaIBGE:
        """Arquiva tentativas com orçamento cooperativo de noventa segundos.

        O orçamento é conferido entre blocos; uma leitura já bloqueada pode
        acrescentar até o timeout HTTP de trinta segundos. Não é um prazo
        absoluto de execução, e a persistência bronze também exige tempo.
        """
        url, parametros = _endereco(recurso, ano)
        agora = datetime.now(UTC)
        identificador = str(uuid4())
        prefixo = f"ibge/{agora.date()}/{identificador}"
        limite = self._relogio() + 90
        espera_servidor = 0.0
        tentativas = []
        situacao = "FALHA"
        for tentativa in range(1, 4):
            espera = max(0.0, self._ultimo_inicio + 1 - self._relogio(), espera_servidor)
            if espera >= limite - self._relogio():
                break
            self._dormir(espera)
            restante = limite - self._relogio()
            if restante <= 0:
                break
            self._ultimo_inicio = self._relogio()
            corpo = bytearray()
            estado = 0
            completo = False
            codificacao = None
            tipo = None
            motivo = None
            espera_servidor = 0.0
            try:
                self._requisicoes += 1
                self._retentativas += int(tentativa > 1)
                with self._transporte.stream(
                    "GET",
                    url,
                    params=parametros,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "User-Agent": "pipeline-etl/0.1.0",
                    },
                    follow_redirects=False,
                    timeout=httpx.Timeout(min(30, restante), connect=min(10, restante)),
                ) as resposta:
                    estado = resposta.status_code
                    codificacao = resposta.headers.get("Content-Encoding")
                    tipo = resposta.headers.get("Content-Type")
                    espera_servidor = interpretar_espera(
                        resposta.headers.get("Retry-After"), datetime.now(UTC)
                    )
                    for bloco in resposta.iter_raw():
                        if len(corpo) + len(bloco) > LIMITE_CORPO or self._relogio() > limite:
                            motivo = "LIMITE_COLETA"
                            break
                        corpo.extend(bloco)
                    else:
                        completo = True
            except (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError):
                motivo = "FALHA_TRANSPORTE"
            objeto_corpo = self._armazenamento.gravar_imutavel(
                f"{prefixo}/tentativa_{tentativa}.body", bytes(corpo)
            )
            metadados = {
                "versao_formato": 1,
                "fonte": "ibge",
                "coleta_id": identificador,
                "recurso": recurso,
                "ano": ano,
                "url": str(httpx.URL(url, params=parametros)),
                "parametros": parametros,
                "status_http": estado,
                "coletado_em": datetime.now(UTC).isoformat(),
                "codificacao_conteudo": codificacao,
                "tipo_conteudo": tipo,
                "completo": completo,
                "corpo": asdict(objeto_corpo),
                "motivo": motivo,
            }
            objeto_meta = self._armazenamento.gravar_imutavel(
                f"{prefixo}/tentativa_{tentativa}.meta.json",
                json.dumps(metadados, ensure_ascii=False).encode(),
            )
            tentativas.append({"corpo": asdict(objeto_corpo), "metadados": asdict(objeto_meta)})
            if estado == 200 and completo and codificacao in (None, "identity"):
                situacao = "COLETADA"
                break
            if motivo == "LIMITE_COLETA" or (estado and estado not in {429, 500, 502, 503, 504}):
                break
            espera_servidor = max(espera_servidor, 2 ** (tentativa - 1))
        manifesto = {
            "versao_formato": 1,
            "fonte": "ibge",
            "coleta_id": identificador,
            "recurso": recurso,
            "ano": ano,
            "situacao": situacao,
            "tentativas": tentativas,
        }
        objeto = self._armazenamento.gravar_imutavel(
            prefixo + "/manifest.json", json.dumps(manifesto, ensure_ascii=False).encode()
        )
        return ResultadoColetaIBGE(objeto, situacao)


def ler_coleta(
    armazenamento: ArmazenamentoObjetos, manifesto: ObjetoBronze
) -> ColetaVerificadaIBGE:
    """Revalida identidade, parâmetros e checksums antes de devolver bytes ao contrato."""
    if manifesto.tamanho_bytes > 65536:
        raise ValueError("Manifesto IBGE excede o limite.")
    conteudo = json.loads(armazenamento.ler(manifesto))
    if (
        conteudo.get("versao_formato") != 1
        or conteudo.get("fonte") != "ibge"
        or conteudo.get("situacao") != "COLETADA"
    ):
        raise ValueError("Coleta IBGE não confirmada.")
    tentativa = conteudo["tentativas"][-1]
    descritor_meta = ObjetoBronze(**tentativa["metadados"])
    descritor_corpo = ObjetoBronze(**tentativa["corpo"])
    if descritor_meta.tamanho_bytes > 65536 or descritor_corpo.tamanho_bytes > LIMITE_CORPO:
        raise ValueError("Artefato IBGE excede os limites.")
    metadados = json.loads(armazenamento.ler(descritor_meta))
    url, parametros = _endereco(conteudo["recurso"], conteudo["ano"])
    coletado = datetime.fromisoformat(metadados["coletado_em"])
    prefixo = manifesto.chave.rsplit("/", 1)[0] + "/"
    if (
        metadados.get("fonte") != "ibge"
        or metadados.get("coleta_id") != conteudo["coleta_id"]
        or metadados.get("recurso") != conteudo["recurso"]
        or metadados.get("ano") != conteudo["ano"]
        or metadados.get("status_http") != 200
        or metadados.get("completo") is not True
        or metadados.get("codificacao_conteudo") not in (None, "identity")
        or metadados.get("corpo") != asdict(descritor_corpo)
        or metadados.get("url") != str(httpx.URL(url, params=parametros))
        or metadados.get("parametros") != parametros
        or coletado.tzinfo is None
        or coletado > datetime.now(UTC)
        or not descritor_corpo.chave.startswith(prefixo)
        or not descritor_meta.chave.startswith(prefixo)
    ):
        raise ValueError("Identidade ou parâmetros IBGE incompatíveis.")
    return ColetaVerificadaIBGE(
        conteudo["recurso"], conteudo["ano"], armazenamento.ler(descritor_corpo), coletado, 200
    )
