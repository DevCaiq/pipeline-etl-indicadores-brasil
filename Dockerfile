FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS construcao
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.13.9
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 --create-home aplicativo
WORKDIR /app
COPY --from=construcao /app/.venv /app/.venv
COPY alembic.ini ./
COPY migracoes ./migracoes
USER aplicativo
CMD ["alembic", "upgrade", "head"]
