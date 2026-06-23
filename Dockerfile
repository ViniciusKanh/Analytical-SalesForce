# ============================================================
# Analytical-Force — Imagem Docker para Hugging Face Spaces
# ------------------------------------------------------------
# Space do tipo "docker". A aplicação (FastAPI/uvicorn) escuta na porta 7860,
# que é a porta esperada pelo HF (definida em app_port no README).
#
# As credenciais NÃO ficam na imagem: são lidas de variáveis de ambiente
# (Secrets do Space). Nunca faça COPY do arquivo .env.
# ============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/user \
    # Cache do Hugging Face (download de modelos) em diretório gravável.
    HF_HOME=/home/user/.cache/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1

# Usuário não-root (HF Spaces executa como uid 1000).
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Dependências (leves): API + agente + cliente de inferência hospedada.
# Sem torch/transformers — a IA usa a Inference API da HF (modelo hospedado).
COPY --chown=user:user requirements-hf.txt ./requirements-hf.txt
RUN pip install --no-cache-dir -r requirements-hf.txt

# Copia o código da aplicação.
COPY --chown=user:user . .

# Garante diretórios graváveis (logs/relatórios/exports são transitórios;
# a persistência real é no Turso). Inclui o cache de modelos do Hugging Face.
RUN mkdir -p logs reports/daily data/exports /home/user/.cache/huggingface \
    && chown -R user:user /home/user

USER user
EXPOSE 7860

# Sobe a API. A porta 7860 deve bater com app_port no README do Space.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7860"]
