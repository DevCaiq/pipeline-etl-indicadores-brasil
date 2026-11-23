"""Erros públicos sem entradas, segredos ou mensagens internas."""

from pydantic import BaseModel


class ErroAPI(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem


class DetalheErro(BaseModel):
    campo: str
    tipo: str
    mensagem: str = "Parâmetro inválido."


class CorpoErro(BaseModel):
    codigo: str
    mensagem: str
    requisicao_id: str
    detalhes: list[DetalheErro] = []


class RespostaErro(BaseModel):
    erro: CorpoErro
