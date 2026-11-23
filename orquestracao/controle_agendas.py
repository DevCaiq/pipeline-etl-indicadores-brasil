"""Marco local de retomada: somente o próprio fluxo pode descartar agenda antiga."""

import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def registrar_marco(raiz: Path, instante: datetime) -> None:
    pasta = raiz / ".cache/prefect"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / "retomada_projeto.json"
    temporario = pasta / (str(uuid4()) + ".tmp")
    try:
        with temporario.open("x", encoding="utf-8") as arquivo:
            json.dump({"instante_utc": instante.isoformat()}, arquivo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def agenda_vencida(raiz: Path, automatica: bool, inicio: datetime | None) -> bool:
    if not automatica or inicio is None:
        return False
    caminho = raiz / ".cache/prefect/retomada_projeto.json"
    if not caminho.exists():
        return False
    marco = datetime.fromisoformat(json.loads(caminho.read_text(encoding="utf-8"))["instante_utc"])
    if marco.tzinfo is None or inicio.tzinfo is None:
        raise ValueError("Datas da retomada precisam informar fuso horário.")
    return inicio < marco
