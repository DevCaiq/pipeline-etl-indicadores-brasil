"""Trava do coordenador e reconciliação conservadora de processos interrompidos."""

import ctypes
import os
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes

from sqlalchemy import Engine, text

CHAVE_COORDENACAO_BCB = 2026111901
CHAVE_COORDENACAO_IBGE = 2026112002


def _consultar_processo_windows(identificador: int) -> bool:
    """API nativa evita execução de comandos e ambiguidade de locale/decodificação."""
    if sys.platform != "win32":
        return True
    biblioteca = ctypes.WinDLL("kernel32", use_last_error=True)
    biblioteca.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    biblioteca.OpenProcess.restype = wintypes.HANDLE
    biblioteca.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    biblioteca.GetExitCodeProcess.restype = wintypes.BOOL
    biblioteca.CloseHandle.argtypes = [wintypes.HANDLE]
    biblioteca.CloseHandle.restype = wintypes.BOOL
    acesso_consulta_limitada = 0x1000
    processo = biblioteca.OpenProcess(acesso_consulta_limitada, False, identificador)
    if not processo:
        # ERROR_INVALID_PARAMETER identifica PID inexistente. Acesso negado é incerteza.
        return ctypes.get_last_error() != 87
    try:
        codigo = wintypes.DWORD()
        sucesso = biblioteca.GetExitCodeProcess(processo, ctypes.byref(codigo))
        return not sucesso or codigo.value == 259  # STILL_ACTIVE
    finally:
        biblioteca.CloseHandle(processo)


def processo_presente(identificador: int) -> bool:
    """Dúvida equivale a presente; a consulta nunca encerra processos."""
    if sys.platform == "win32":
        try:
            return _consultar_processo_windows(identificador)
        except (OSError, UnicodeError):
            return True
    try:
        os.kill(identificador, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _recuperar(motor: Engine, modo: str = "pipeline_bcb") -> None:
    with motor.begin() as conexao:
        pendentes = conexao.execute(
            text(
                "SELECT p.execucao_id,p.parametros FROM ops.execucao p "
                "WHERE p.modo=:modo AND (p.situacao='EM_EXECUCAO' OR EXISTS("
                "SELECT 1 FROM ops.execucao f WHERE f.situacao='EM_EXECUCAO' "
                "AND f.parametros->>'pai_pipeline_id'=p.execucao_id::text))"
            ),
            {"modo": modo},
        ).all()
        for identificador, parametros in pendentes:
            processo = parametros.get("processo_id")
            if (
                parametros.get("maquina") != socket.gethostname()
                or not isinstance(processo, int)
                or isinstance(processo, bool)
                or processo <= 0
                or processo_presente(processo)
            ):
                continue
            conexao.execute(
                text(
                    "UPDATE ops.execucao SET situacao='FALHA', "
                    "finalizado_em=now(),erro='PROCESSO_INTERROMPIDO_CONFIRMADO' "
                    "WHERE situacao='EM_EXECUCAO' AND (execucao_id=:id OR "
                    "parametros->>'pai_pipeline_id'=:pai)"
                ),
                {"id": identificador, "pai": str(identificador)},
            )


@contextmanager
def proteger_coordenacao(motor: Engine, dominio: str = "bcb") -> Iterator[None]:
    """Trava de sessão durante todo o fluxo, além das travas de promoção existentes."""
    if dominio not in {"bcb", "ibge"}:
        raise ValueError("Domínio de coordenação inválido.")
    chave = CHAVE_COORDENACAO_BCB if dominio == "bcb" else CHAVE_COORDENACAO_IBGE
    with motor.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        try:
            adquirida = conexao.scalar(
                text("SELECT pg_try_advisory_lock(:chave)"), {"chave": chave}
            )
        except BaseException:
            conexao.invalidate()
            raise
        if not adquirida:
            raise RuntimeError(f"Outro coordenador {dominio.upper()} está ativo; execução adiada.")
        try:
            _recuperar(motor, "pipeline_" + dominio)
            yield
        finally:
            try:
                liberada = conexao.scalar(
                    text("SELECT pg_advisory_unlock(:chave)"), {"chave": chave}
                )
                if liberada is not True:
                    conexao.invalidate()
            except BaseException:
                conexao.invalidate()
                raise
