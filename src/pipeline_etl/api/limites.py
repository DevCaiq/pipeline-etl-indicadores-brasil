"""Limite por endereço real de conexão, em um único processo."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable


class LimitadorLocal:
    def __init__(self, limite: int, relogio: Callable[[], float] = time.monotonic):
        self.limite = limite
        self.relogio = relogio
        self.clientes: dict[str, deque[float]] = {}
        self.trava = threading.Lock()

    def conferir(self, cliente: str) -> int:
        with self.trava:
            agora = self.relogio()
            if cliente not in self.clientes and len(self.clientes) >= 4096:
                self.clientes = {
                    chave: fila
                    for chave, fila in self.clientes.items()
                    if fila and fila[-1] > agora - 60
                }
                if len(self.clientes) >= 4096:
                    return 60
            fila = self.clientes.setdefault(cliente, deque())
            while fila and fila[0] <= agora - 60:
                fila.popleft()
            if len(fila) >= self.limite:
                return max(1, math.ceil(60 - (agora - fila[0])))
            fila.append(agora)
            return 0
