"""Testa o envio de e-mail via Gmail API (OAuth refresh token).

Valida as credenciais antes do deploy. Envia um e-mail curto de teste.

Uso:
    python scripts/test_gmail_oauth.py

Variáveis necessárias no .env:
    GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN,
    GMAIL_SENDER (remetente autorizado), REPORT_RECIPIENT_EMAIL (destinatário).

Não imprime tokens nem segredos.
"""

import base64
import os
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
SENDER = os.getenv("GMAIL_SENDER", "")
RECIPIENT = os.getenv("REPORT_RECIPIENT_EMAIL", "")


def validar() -> None:
    """Confere se as variáveis obrigatórias estão preenchidas."""
    faltando = [
        nome
        for nome, valor in {
            "GMAIL_CLIENT_ID": CLIENT_ID,
            "GMAIL_CLIENT_SECRET": CLIENT_SECRET,
            "GMAIL_REFRESH_TOKEN": REFRESH_TOKEN,
            "GMAIL_SENDER": SENDER,
            "REPORT_RECIPIENT_EMAIL": RECIPIENT,
        }.items()
        if not valor
    ]
    if faltando:
        raise SystemExit(f"Variáveis ausentes no .env: {', '.join(faltando)}")


def obter_access_token() -> str:
    """Troca o refresh token por um access token (sem imprimir segredos)."""
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        try:
            erro = resp.json()
            detalhe = f"{erro.get('error')} - {erro.get('error_description', '')}"
        except ValueError:
            detalhe = "resposta inválida do servidor OAuth."
        print("Falha no OAuth do Google. Status:", resp.status_code, "-", detalhe.strip(" -"))
        raise SystemExit(1)
    return resp.json()["access_token"]


def main() -> None:
    """Executa o teste de envio."""
    validar()
    print("Obtendo access token do Google...")
    token = obter_access_token()
    print("Access token obtido com sucesso.")

    mensagem = MIMEText(
        "Teste de envio do Analytical-Force via Gmail API. Se você recebeu, está funcionando.",
        "plain",
        "utf-8",
    )
    mensagem["Subject"] = "Analytical-Force — Teste Gmail API"
    mensagem["From"] = SENDER
    mensagem["To"] = RECIPIENT
    raw = base64.urlsafe_b64encode(mensagem.as_bytes()).decode("utf-8")

    resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"raw": raw},
        timeout=30,
    )
    if resp.status_code >= 400:
        print("Falha ao enviar. Status:", resp.status_code, "-", resp.text[:300])
        raise SystemExit(1)
    print(f"E-mail de teste enviado com sucesso para {RECIPIENT}.")


if __name__ == "__main__":
    main()
