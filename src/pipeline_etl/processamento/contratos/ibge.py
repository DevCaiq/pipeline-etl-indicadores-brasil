"""Normalização pura dos contratos oficiais homologados do IBGE."""

import json
import re
from dataclasses import dataclass
from typing import Any, TypeVar


class ErroContratoIBGE(ValueError):
    """Resposta incompatível com o contrato homologado do IBGE."""


@dataclass(frozen=True)
class RegiaoValidada:
    codigo: int
    sigla: str
    nome: str


@dataclass(frozen=True)
class UFValidada:
    codigo: int
    sigla: str
    nome: str
    regiao_codigo: int


@dataclass(frozen=True)
class MunicipioValidado:
    codigo_ibge: str
    nome: str
    uf_codigo: int


@dataclass(frozen=True)
class PopulacaoValidada:
    codigo_ibge: str
    ano: int
    populacao: int | None
    marcador: str | None
    motivo: str | None


@dataclass(frozen=True)
class LocalidadesValidadas:
    regioes: tuple[RegiaoValidada, ...]
    ufs: tuple[UFValidada, ...]
    municipios: tuple[MunicipioValidado, ...]


_Tipo = TypeVar("_Tipo")


def _objeto(valor: Any) -> dict[str, Any]:
    if not isinstance(valor, dict):
        raise ErroContratoIBGE("Objeto JSON esperado.")
    return valor


def _lista(valor: Any) -> list[Any]:
    if not isinstance(valor, list) or not valor:
        raise ErroContratoIBGE("Lista JSON não vazia esperada.")
    return valor


def _pares(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    for chave, valor in pares:
        if chave in resultado:
            raise ErroContratoIBGE("Chave JSON duplicada.")
        resultado[chave] = valor
    return resultado


def _ler(corpo: bytes) -> Any:
    try:
        return json.loads(corpo.decode("utf-8"), object_pairs_hook=_pares)
    except (UnicodeError, json.JSONDecodeError) as erro:
        raise ErroContratoIBGE("Corpo deve conter JSON UTF-8 válido.") from erro


def _inteiro(valor: Any) -> int:
    if type(valor) is not int or valor <= 0:
        raise ErroContratoIBGE("Identificador inteiro positivo esperado.")
    return valor


def _texto(valor: Any) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroContratoIBGE("Texto não vazio esperado.")
    return valor


def _codigo(valor: Any) -> str:
    if not isinstance(valor, str) or re.fullmatch(r"[0-9]{7}", valor) is None:
        raise ErroContratoIBGE("Código municipal deve conter sete dígitos.")
    return valor


def _inserir[Tipo](mapa: dict[Any, Tipo], chave: Any, valor: Tipo) -> None:
    if chave in mapa and mapa[chave] != valor:
        raise ErroContratoIBGE("Identificador duplicado com conteúdo conflitante.")
    mapa[chave] = valor


def normalizar_localidades(
    corpo_regioes: bytes, corpo_ufs: bytes, corpo_municipios: bytes
) -> LocalidadesValidadas:
    """Valida referências territoriais e ordena snapshot sem inferir hierarquia histórica."""
    regioes: dict[int, RegiaoValidada] = {}
    ufs: dict[int, UFValidada] = {}
    municipios: dict[str, MunicipioValidado] = {}
    for entrada in _lista(_ler(corpo_regioes)):
        objeto = _objeto(entrada)
        regiao = RegiaoValidada(
            _inteiro(objeto.get("id")), _texto(objeto.get("sigla")), _texto(objeto.get("nome"))
        )
        _inserir(regioes, regiao.codigo, regiao)

    def conferir_regiao(entrada: Any) -> int:
        objeto = _objeto(entrada)
        codigo = _inteiro(objeto.get("id"))
        if codigo not in regioes or regioes[codigo] != RegiaoValidada(
            codigo, _texto(objeto.get("sigla")), _texto(objeto.get("nome"))
        ):
            raise ErroContratoIBGE("Referência regional ausente ou conflitante.")
        return codigo

    for entrada in _lista(_ler(corpo_ufs)):
        objeto = _objeto(entrada)
        uf = UFValidada(
            _inteiro(objeto.get("id")),
            _texto(objeto.get("sigla")),
            _texto(objeto.get("nome")),
            conferir_regiao(objeto.get("regiao")),
        )
        _inserir(ufs, uf.codigo, uf)
    for entrada in _lista(_ler(corpo_municipios)):
        objeto = _objeto(entrada)
        codigo = _codigo(str(_inteiro(objeto.get("id"))))
        referencias: list[int] = []
        for caminho in (
            ("microrregiao", "mesorregiao", "UF"),
            ("regiao-imediata", "regiao-intermediaria", "UF"),
        ):
            atual: Any = objeto
            for chave in caminho:
                if atual is None:
                    break
                atual = _objeto(atual).get(chave)
            if atual is None:
                continue
            referencia = _objeto(atual)
            codigo_uf = _inteiro(referencia.get("id"))
            candidata = UFValidada(
                codigo_uf,
                _texto(referencia.get("sigla")),
                _texto(referencia.get("nome")),
                conferir_regiao(referencia.get("regiao")),
            )
            if ufs.get(codigo_uf) != candidata:
                raise ErroContratoIBGE("Referência de UF ausente ou conflitante.")
            referencias.append(codigo_uf)
        if not referencias or len(set(referencias)) != 1:
            raise ErroContratoIBGE("Município sem UF/região ou com hierarquias conflitantes.")
        municipio = MunicipioValidado(codigo, _texto(objeto.get("nome")), referencias[0])
        _inserir(municipios, codigo, municipio)
    return LocalidadesValidadas(
        tuple(regioes[chave] for chave in sorted(regioes)),
        tuple(ufs[chave] for chave in sorted(ufs)),
        tuple(municipios[chave] for chave in sorted(municipios)),
    )


def descobrir_periodos(corpo: bytes) -> tuple[int, ...]:
    """Descobre os anos publicados desde 2020, sem preencher lacunas."""
    periodos: dict[int, dict[str, Any]] = {}
    for entrada in _lista(_ler(corpo)):
        objeto = _objeto(entrada)
        identificador = objeto.get("id")
        if not isinstance(identificador, str) or re.fullmatch(r"[0-9]{4}", identificador) is None:
            raise ErroContratoIBGE("Período anual inválido.")
        ano = int(identificador)
        _inserir(periodos, ano, objeto)
    return tuple(ano for ano in sorted(periodos) if ano >= 2020)


def validar_metadados(corpo: bytes) -> None:
    """Exige tabela, variável, unidade e nível homologados."""
    objeto = _objeto(_ler(corpo))
    if type(objeto.get("id")) is not int or objeto["id"] != 6579:
        raise ErroContratoIBGE("Tabela diferente de 6579.")
    if objeto.get("classificacoes") != []:
        raise ErroContratoIBGE("Classificações não homologadas.")
    if _objeto(objeto.get("periodicidade")).get("frequencia") != "anual":
        raise ErroContratoIBGE("Frequência diferente de anual.")
    niveis = _objeto(objeto.get("nivelTerritorial")).get("Administrativo")
    if not isinstance(niveis, list) or "N6" not in niveis:
        raise ErroContratoIBGE("Nível municipal N6 ausente.")
    variaveis = _lista(objeto.get("variaveis"))
    if len(variaveis) != 1:
        raise ErroContratoIBGE("Conjunto de variáveis não homologado.")
    variavel = _objeto(variaveis[0])
    if type(variavel.get("id")) is not int or variavel["id"] != 9324:
        raise ErroContratoIBGE("Variável diferente de 9324.")
    if variavel.get("unidade") != "Pessoas":
        raise ErroContratoIBGE("Unidade diferente de Pessoas.")


def normalizar_populacao(
    corpo: bytes, anos: set[int], municipios: set[str]
) -> tuple[PopulacaoValidada, ...]:
    """Normaliza inteiros e marcador real, exigindo cobertura contratada exata."""
    if not anos or any(type(ano) is not int or not 2020 <= ano <= 9999 for ano in anos):
        raise ErroContratoIBGE("Anos esperados inválidos.")
    if not municipios:
        raise ErroContratoIBGE("Municípios esperados ausentes.")
    for codigo in municipios:
        _codigo(codigo)
    envelope = _lista(_ler(corpo))
    if len(envelope) != 1:
        raise ErroContratoIBGE("Envelope de variável não homologado.")
    objeto = _objeto(envelope[0])
    if objeto.get("id") != "9324" or objeto.get("unidade") != "Pessoas":
        raise ErroContratoIBGE("Variável/unidade de população inválida.")
    linhas: dict[tuple[str, int], PopulacaoValidada] = {}
    for entrada in _lista(objeto.get("resultados")):
        resultado = _objeto(entrada)
        if resultado.get("classificacoes") != []:
            raise ErroContratoIBGE("Classificações não homologadas.")
        for entrada_serie in _lista(resultado.get("series")):
            serie = _objeto(entrada_serie)
            localidade = _objeto(serie.get("localidade"))
            codigo = _codigo(localidade.get("id"))
            if codigo not in municipios or _objeto(localidade.get("nivel")).get("id") != "N6":
                raise ErroContratoIBGE("Município ou nível fora do conjunto esperado.")
            valores = _objeto(serie.get("serie"))
            if set(valores) != {str(ano) for ano in anos}:
                raise ErroContratoIBGE("Anos retornados diferentes dos esperados.")
            for ano in sorted(anos):
                valor = valores[str(ano)]
                if valor == "...":
                    linha = PopulacaoValidada(codigo, ano, None, valor, "DADO_NAO_DISPONIVEL")
                elif isinstance(valor, str) and re.fullmatch(r"[0-9]+", valor):
                    if len(valor) > 19 or int(valor) > 9223372036854775807:
                        raise ErroContratoIBGE("População excede BIGINT.")
                    linha = PopulacaoValidada(codigo, ano, int(valor), None, None)
                else:
                    raise ErroContratoIBGE("Valor ou marcador de população não homologado.")
                _inserir(linhas, (codigo, ano), linha)
    if {codigo for codigo, _ in linhas} != municipios:
        raise ErroContratoIBGE("Cobertura municipal incompleta.")
    return tuple(linhas[chave] for chave in sorted(linhas))
