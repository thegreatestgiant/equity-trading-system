FROM python:3.14-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

EXPOSE 8501

ENV BACKEND_URL=http://localhost:8000

CMD ["uv", "run", "streamlit", "run", "app_ui.py", "--server.address=0.0.0.0", "--server.port=8501"]