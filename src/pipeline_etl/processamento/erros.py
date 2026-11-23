"""Falhas operacionais com mensagens seguras e rastreabilidade local."""

from datetime import datetime
from pathlib import Path


class ErroColeta(Exception):
    """Indica falha sem autorizar novas tentativas automáticas de toda a etapa."""

    def __init__(self, mensagem: str, manifesto: Path | None = None) -> None:
        super().__init__(mensagem)
        self.manifesto = manifesto


class ColetaAdiada(ErroColeta):
    """Preserva a próxima tentativa elegível quando a espera excede o orçamento."""

    def __init__(self, proxima_tentativa_em: datetime) -> None:
        super().__init__("Coleta adiada para respeitar a espera e o orçamento de tempo.")
        self.proxima_tentativa_em = proxima_tentativa_em
