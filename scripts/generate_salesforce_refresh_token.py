"""
Gera o SALESFORCE_REFRESH_TOKEN usando OAuth Authorization Code Flow com PKCE.

Uso:
    python scripts/generate_salesforce_refresh_token.py

Pré-requisitos no .env:
    SALESFORCE_INSTANCE_URL=https://pensotecnologia.my.salesforce.com
    SALESFORCE_CLIENT_ID=...
    SALESFORCE_CLIENT_SECRET=...

Callback URL configurado na External Client App:
    http://localhost:8080/callback

Observação:
    Este script não altera dados no Salesforce.
    Ele apenas autentica e gera o refresh_token.
"""

import base64
import hashlib
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import load_dotenv


# Carrega variáveis do .env
load_dotenv()

SALESFORCE_INSTANCE_URL = os.getenv("SALESFORCE_INSTANCE_URL", "").rstrip("/")
SALESFORCE_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID", "")
SALESFORCE_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET", "")

CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8080
CALLBACK_PATH = "/callback"
CALLBACK_URL = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"

AUTH_CODE = None
AUTH_ERROR = None
AUTH_STATE_RECEIVED = None


def validar_configuracoes() -> None:
    """Valida se as variáveis mínimas estão configuradas."""
    if not SALESFORCE_INSTANCE_URL:
        raise ValueError("SALESFORCE_INSTANCE_URL não está configurado no .env.")

    if not SALESFORCE_CLIENT_ID:
        raise ValueError("SALESFORCE_CLIENT_ID não está configurado no .env.")

    if not SALESFORCE_CLIENT_SECRET:
        raise ValueError("SALESFORCE_CLIENT_SECRET não está configurado no .env.")


def gerar_code_verifier() -> str:
    """
    Gera o code_verifier usado no PKCE.

    O PKCE aumenta a segurança do fluxo OAuth.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("utf-8").rstrip("=")


def gerar_code_challenge(code_verifier: str) -> str:
    """Gera o code_challenge S256 a partir do code_verifier."""
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Servidor local simples para receber o callback do Salesforce."""

    def do_GET(self) -> None:
        global AUTH_CODE, AUTH_ERROR, AUTH_STATE_RECEIVED

        parsed_url = urllib.parse.urlparse(self.path)

        if parsed_url.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Rota nao encontrada.")
            return

        query_params = urllib.parse.parse_qs(parsed_url.query)

        AUTH_CODE = query_params.get("code", [None])[0]
        AUTH_ERROR = query_params.get("error", [None])[0]
        AUTH_STATE_RECEIVED = query_params.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        if AUTH_CODE:
            mensagem = """
            <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>Autorização concluída com sucesso.</h2>
                    <p>Você pode voltar ao terminal.</p>
                </body>
            </html>
            """
        else:
            mensagem = """
            <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>Falha na autorização.</h2>
                    <p>Volte ao terminal para ver o erro.</p>
                </body>
            </html>
            """

        self.wfile.write(mensagem.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        """Evita poluir o terminal com logs HTTP."""
        return


def iniciar_servidor_callback() -> HTTPServer:
    """Inicia o servidor local para capturar o callback OAuth."""
    servidor = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), OAuthCallbackHandler)

    thread = threading.Thread(target=servidor.serve_forever)
    thread.daemon = True
    thread.start()

    return servidor


def montar_url_autorizacao(code_challenge: str, state: str) -> str:
    """Monta a URL de autorização do Salesforce."""
    parametros = {
        "response_type": "code",
        "client_id": SALESFORCE_CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "scope": "api refresh_token",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    query_string = urllib.parse.urlencode(parametros)

    return f"{SALESFORCE_INSTANCE_URL}/services/oauth2/authorize?{query_string}"


def trocar_code_por_tokens(auth_code: str, code_verifier: str) -> dict:
    """Troca o authorization code por access_token e refresh_token."""
    token_url = f"{SALESFORCE_INSTANCE_URL}/services/oauth2/token"

    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": SALESFORCE_CLIENT_ID,
        "client_secret": SALESFORCE_CLIENT_SECRET,
        "redirect_uri": CALLBACK_URL,
        "code_verifier": code_verifier,
    }

    resposta = requests.post(token_url, data=payload, timeout=30)

    if resposta.status_code != 200:
        print("\nFalha ao trocar authorization code por tokens.")
        print("Status:", resposta.status_code)
        print("Resposta:", resposta.text)
        raise SystemExit(1)

    return resposta.json()


def main() -> None:
    """Executa o fluxo completo de geração do refresh token."""
    validar_configuracoes()

    print("Iniciando geração do Salesforce Refresh Token...")
    print(f"Instance URL: {SALESFORCE_INSTANCE_URL}")
    print(f"Callback URL: {CALLBACK_URL}")
    print("Nenhum dado do Salesforce será criado, editado ou excluído.")

    code_verifier = gerar_code_verifier()
    code_challenge = gerar_code_challenge(code_verifier)
    state = secrets.token_urlsafe(32)

    servidor = iniciar_servidor_callback()

    try:
        authorization_url = montar_url_autorizacao(code_challenge, state)

        print("\nAbrindo navegador para autorização Salesforce...")
        print("Se o navegador não abrir, copie e cole esta URL:")
        print(authorization_url)

        webbrowser.open(authorization_url)

        print("\nAguardando callback em http://localhost:8080/callback ...")

        timeout_segundos = 180
        inicio = time.time()

        while AUTH_CODE is None and AUTH_ERROR is None:
            if time.time() - inicio > timeout_segundos:
                raise TimeoutError("Tempo limite excedido aguardando autorização OAuth.")
            time.sleep(1)

        if AUTH_ERROR:
            raise RuntimeError(f"Salesforce retornou erro na autorização: {AUTH_ERROR}")

        if AUTH_STATE_RECEIVED != state:
            raise RuntimeError("State OAuth inválido. Possível problema de segurança na autorização.")

        print("Authorization code recebido com sucesso.")
        print("Trocando authorization code por tokens...")

        tokens = trocar_code_por_tokens(AUTH_CODE, code_verifier)

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        instance_url = tokens.get("instance_url")

        if not access_token:
            raise RuntimeError("O Salesforce não retornou access_token.")

        if not refresh_token:
            print("\nO Salesforce retornou access_token, mas não retornou refresh_token.")
            print("Verifique se a External Client App possui o escopo:")
            print("- Perform requests at any time (refresh_token, offline_access)")
            print("\nTambém confirme se a política da app permite refresh token.")
            raise SystemExit(1)

        print("\nRefresh token gerado com sucesso.")
        print("\nCole esta linha no seu arquivo .env:\n")
        print(f'SALESFORCE_REFRESH_TOKEN="{refresh_token}"')

        if instance_url:
            print("\nConfirme também esta linha no .env:")
            print(f'SALESFORCE_INSTANCE_URL="{instance_url}"')

        print("\nAtenção: não envie este token para GitHub, chat, print ou e-mail.")

    finally:
        servidor.shutdown()
        servidor.server_close()


if __name__ == "__main__":
    main()