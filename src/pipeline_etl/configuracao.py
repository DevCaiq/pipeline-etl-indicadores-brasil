"""Configuração tipada, sem efeitos de rede ou criação de diretórios."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class ConfiguracaoAplicacao(BaseSettings):
    """Carrega opções próprias de variáveis de ambiente e do arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        hide_input_in_errors=True,
        frozen=True,
    )

    cache_habilitado: bool = False
    url_redis: SecretStr | None = None

    segredo_cursor: SecretStr | None = None
    limite_requisicoes_minuto: int = Field(default=100, ge=1, le=100000)

    host_banco_migracoes: str | None = None
    senha_banco_migracoes: SecretStr | None = None
    url_banco_publicador: SecretStr | None = None
    url_banco_api: SecretStr | None = None
    url_banco_processamento: SecretStr | None = None
    url_banco_migracoes: SecretStr | None = None

    ambiente: Literal["desenvolvimento", "teste", "producao"] = "desenvolvimento"
    nivel_registros: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    caminho_bronze: Path = Path("dados/bronze")
    series_bcb: Annotated[tuple[int, ...], NoDecode] = (432, 433, 1)

    @field_validator("nivel_registros", mode="before")
    @classmethod
    def normalizar_nivel(cls, valor: object) -> object:
        """Aceita níveis convencionais sem diferenciar maiúsculas/minúsculas."""
        return valor.strip().upper() if isinstance(valor, str) else valor

    @field_validator("caminho_bronze", mode="before")
    @classmethod
    def validar_caminho(cls, valor: object) -> object:
        """Evita que um caminho vazio seja interpretado como diretório atual."""
        if isinstance(valor, str) and not valor.strip():
            raise ValueError("O caminho da camada bronze não pode ser vazio.")
        return valor

    @field_validator("series_bcb", mode="before")
    @classmethod
    def interpretar_series(cls, valor: object) -> object:
        """Converte a seleção CSV da configuração, preservando a ordem."""
        if isinstance(valor, str):
            try:
                return tuple(int(item.strip()) for item in valor.split(","))
            except ValueError as erro:
                raise ValueError("Informe códigos de séries separados por vírgulas.") from erro
        return valor

    @field_validator("series_bcb")
    @classmethod
    def validar_series(cls, series: tuple[int, ...]) -> tuple[int, ...]:
        """Restringe a seleção às séries homologadas, sem duplicidades."""
        if not series or not set(series).issubset({432, 433, 1}):
            raise ValueError("Selecione ao menos uma das séries BCB: 432, 433 e 1.")
        if len(series) != len(set(series)):
            raise ValueError("Não repita códigos de séries BCB.")
        return series

    @field_validator(
        "url_banco_api", "url_banco_processamento", "url_banco_migracoes", "url_banco_publicador"
    )
    @classmethod
    def validar_url_banco(cls, valor: SecretStr | None) -> SecretStr | None:
        """Aceita somente o driver PostgreSQL previsto e mantém senhas protegidas."""
        if valor is None:
            return None
        try:
            endereco = make_url(valor.get_secret_value())
            if endereco.drivername != "postgresql+psycopg" or not endereco.database:
                raise ValueError("Driver ou banco incompatível.")
        except (ArgumentError, ValueError) as erro:
            raise ValueError("Informe uma URL PostgreSQL com driver postgresql+psycopg.") from erro
        return valor

    @model_validator(mode="after")
    def validar_origem_migracoes(self) -> Self:
        """Evita credencial parcial ou duas origens concorrentes para o migrador."""
        possui_partes = (
            self.host_banco_migracoes is not None or self.senha_banco_migracoes is not None
        )
        if self.url_banco_migracoes is not None and possui_partes:
            raise ValueError("Use URL_BANCO_MIGRACOES ou host/senha separados, não ambos.")
        if (self.host_banco_migracoes is None) != (self.senha_banco_migracoes is None):
            raise ValueError("Informe host e senha do migrador em conjunto.")
        return self

    @model_validator(mode="after")
    def validar_cache(self) -> Self:
        """Exige uma URL Redis válida somente quando o cache estiver habilitado."""
        from urllib.parse import urlsplit

        if self.cache_habilitado:
            if self.url_redis is None:
                raise ValueError("Defina URL_REDIS ao habilitar o cache.")
            try:
                endereco = urlsplit(self.url_redis.get_secret_value())
                if (
                    endereco.scheme not in {"redis", "rediss"}
                    or not endereco.hostname
                    or endereco.query
                ):
                    raise ValueError()
                if endereco.port == 0:
                    raise ValueError()
            except ValueError:
                raise ValueError("Informe uma URL Redis válida.") from None
        return self

    def obter_url_migracoes(self) -> SecretStr:
        """Constrói DSN sem interpretar caracteres reservados da senha como URL."""
        if self.url_banco_migracoes is not None:
            return self.url_banco_migracoes
        if self.host_banco_migracoes is None or self.senha_banco_migracoes is None:
            raise ValueError("Defina URL_BANCO_MIGRACOES ou host/senha do migrador.")
        endereco = URL.create(
            "postgresql+psycopg",
            username="migracoes",
            password=self.senha_banco_migracoes.get_secret_value(),
            host=self.host_banco_migracoes,
            port=5432,
            database="etl",
        )
        return SecretStr(endereco.render_as_string(hide_password=False))
