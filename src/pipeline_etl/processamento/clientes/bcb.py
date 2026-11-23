"""Cliente SGS síncrono com retentativas seletivas e espera controlada."""

import math
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
import structlog
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from pipeline_etl.processamento.erros import ColetaAdiada, ErroColeta
from pipeline_etl.processamento.tipos import RespostaBCB


def falha_transitoria(erro: BaseException) -> bool:
    """Restringe retry a rede, timeout e status explicitamente transitórios."""
    if isinstance(erro, httpx.HTTPStatusError):
        return erro.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(erro, (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError))


def interpretar_espera(valor: str | None, agora: datetime) -> float:
    """Interpreta Retry-After em segundos inteiros ou data HTTP."""
    if valor is None:
        return 0.0
    try:
        return max(0.0, float(int(valor.strip())))
    except OverflowError:
        return float("inf")
    except ValueError:
        try:
            instante = parsedate_to_datetime(valor)
            if instante.tzinfo is None:
                instante = instante.replace(tzinfo=UTC)
            return max(0.0, (instante - agora).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0.0


def proxima_tentativa(agora: datetime, espera: float) -> datetime:
    """Representa esperas além do calendário sem antecipar uma nova consulta."""
    try:
        return agora + timedelta(seconds=espera)
    except OverflowError:
        return datetime.max.replace(tzinfo=UTC)


class ClienteBCB:
    """Reutiliza cliente HTTP externo; o chamador controla seu fechamento."""

    def __init__(
        self,
        cliente_http: httpx.Client,
        *,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.monotonic,
        agora: Callable[[], datetime] | None = None,
        orcamento_segundos: float = 180.0,
        limite_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        if not math.isfinite(orcamento_segundos) or orcamento_segundos <= 0 or limite_bytes <= 0:
            raise ValueError("Orçamento e limite do corpo devem ser positivos e finitos.")
        self._cliente = cliente_http
        self._dormir = dormir
        self._relogio = relogio
        self._agora = agora or (lambda: datetime.now(UTC))
        self._orcamento = orcamento_segundos
        self._limite_bytes = limite_bytes
        self._ultimo_inicio = float("-inf")
        self._proximo_inicio = float("-inf")
        self._trava = threading.Lock()
        self._requisicoes = 0
        self._retentativas = 0
        self._tentativas_consulta = 0

    @property
    def metricas_coleta(self) -> dict[str, int]:
        """Devolve cópia dos contadores de tentativas efetivamente iniciadas."""
        return {"requisicoes": self._requisicoes, "retentativas": self._retentativas}

    def buscar(self, codigo: int, inicio: date, fim: date) -> RespostaBCB:
        """Busca uma janela contida no mesmo ano civil, sem interpretar JSON."""
        if codigo not in {432, 433, 1} or inicio > fim or inicio.year != fim.year:
            raise ValueError("Série ou janela BCB inválida; use uma janela por ano civil.")
        with self._trava:
            self._tentativas_consulta = 0
            limite = self._relogio() + self._orcamento
            espera_base = wait_exponential_jitter(initial=1, max=30)

            def calcular_espera(estado: RetryCallState) -> float:
                erro = estado.outcome.exception() if estado.outcome is not None else None
                espera = float(espera_base(estado))
                if isinstance(erro, httpx.HTTPStatusError):
                    espera = max(
                        espera,
                        interpretar_espera(erro.response.headers.get("Retry-After"), self._agora()),
                    )
                structlog.get_logger(servico="coleta", fonte="bcb").warning(
                    "Tentativa BCB sem resposta válida",
                    codigo_serie=codigo,
                    tentativa=estado.attempt_number,
                    tipo_falha=type(erro).__name__,
                    status_http=erro.response.status_code
                    if isinstance(erro, httpx.HTTPStatusError)
                    else None,
                    espera_segundos=espera if math.isfinite(espera) else None,
                )
                if espera >= limite - self._relogio():
                    raise ColetaAdiada(proxima_tentativa(self._agora(), espera))
                return espera

            def registrar_tentativa(estado: RetryCallState) -> None:
                structlog.get_logger(servico="coleta", fonte="bcb").info(
                    "Consulta BCB iniciada",
                    codigo_serie=codigo,
                    tentativa=estado.attempt_number,
                    url=f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados",
                    data_inicial=inicio.isoformat(),
                    data_final=fim.isoformat(),
                )

            repetidor = Retrying(
                stop=stop_after_attempt(5),
                retry=retry_if_exception(falha_transitoria),
                wait=calcular_espera,
                sleep=self._dormir,
                before=registrar_tentativa,
                reraise=True,
            )
            try:
                resposta: RespostaBCB = repetidor(self._consultar, codigo, inicio, fim, limite)
                return resposta
            except httpx.HTTPError as erro:
                status = (
                    erro.response.status_code if isinstance(erro, httpx.HTTPStatusError) else None
                )
                mensagem = (
                    f"Consulta BCB falhou (HTTP {status})."
                    if status
                    else "Falha de comunicação com o BCB."
                )
                raise ErroColeta(mensagem) from erro

    def _restante(self, limite: float) -> float:
        restante = limite - self._relogio()
        if restante <= 0:
            raise ErroColeta("Consulta excedeu o orçamento de tempo.")
        return restante

    def _consultar(self, codigo: int, inicio: date, fim: date, limite: float) -> RespostaBCB:
        espera = max(0.0, max(self._ultimo_inicio + 1.0, self._proximo_inicio) - self._relogio())
        if espera:
            if espera >= self._restante(limite):
                raise ColetaAdiada(proxima_tentativa(self._agora(), espera))
            self._dormir(espera)
        restante = self._restante(limite)
        self._ultimo_inicio = self._relogio()
        parametros = {
            "formato": "json",
            "dataInicial": inicio.strftime("%d/%m/%Y"),
            "dataFinal": fim.strftime("%d/%m/%Y"),
        }
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
        tempo_limite = httpx.Timeout(
            connect=min(10, restante),
            read=min(30, restante),
            write=min(30, restante),
            pool=min(10, restante),
        )
        self._requisicoes += 1
        self._retentativas += int(self._tentativas_consulta > 0)
        self._tentativas_consulta += 1
        with self._cliente.stream(
            "GET",
            url,
            params=parametros,
            timeout=tempo_limite,
            follow_redirects=False,
            headers={
                "User-Agent": "pipeline-etl/0.1.0",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
        ) as resposta:
            if resposta.is_error:
                espera_servidor = interpretar_espera(
                    resposta.headers.get("Retry-After"), self._agora()
                )
                self._proximo_inicio = max(self._proximo_inicio, self._relogio() + espera_servidor)
            resposta.raise_for_status()
            corpo = bytearray()
            for bloco in resposta.iter_raw():
                self._restante(limite)
                if len(corpo) + len(bloco) > self._limite_bytes:
                    raise ErroColeta("Resposta BCB excedeu o limite de bytes.")
                corpo.extend(bloco)
            self._restante(limite)
            return RespostaBCB(
                codigo,
                bytes(corpo),
                str(httpx.URL(url, params=parametros)),
                parametros,
                resposta.status_code,
                self._agora(),
                resposta.headers.get("Content-Type"),
                resposta.headers.get("Content-Encoding"),
            )
