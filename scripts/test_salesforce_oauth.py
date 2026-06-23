import os
import requests
from dotenv import load_dotenv
from simple_salesforce import Salesforce


load_dotenv()

SALESFORCE_INSTANCE_URL = os.getenv("SALESFORCE_INSTANCE_URL", "").rstrip("/")
SALESFORCE_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID", "")
SALESFORCE_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET", "")
SALESFORCE_REFRESH_TOKEN = os.getenv("SALESFORCE_REFRESH_TOKEN", "")
SALESFORCE_API_VERSION = os.getenv("SALESFORCE_API_VERSION", "64.0")


def obter_access_token() -> dict:
    """Obtém access_token usando refresh_token."""
    token_url = f"{SALESFORCE_INSTANCE_URL}/services/oauth2/token"

    payload = {
        "grant_type": "refresh_token",
        "client_id": SALESFORCE_CLIENT_ID,
        "client_secret": SALESFORCE_CLIENT_SECRET,
        "refresh_token": SALESFORCE_REFRESH_TOKEN,
    }

    resposta = requests.post(token_url, data=payload, timeout=30)

    if resposta.status_code != 200:
        # Mensagem sanitizada: apenas 'error'/'error_description' (sem tokens).
        try:
            erro = resposta.json()
            detalhe = (
                f"{erro.get('error', 'erro_desconhecido')} — "
                f"{erro.get('error_description', '')}"
            ).strip(" —")
        except ValueError:
            detalhe = "resposta inválida do servidor OAuth."
        print("Falha ao obter access token.")
        print("Status:", resposta.status_code)
        print("Detalhe:", detalhe)
        raise SystemExit(1)

    return resposta.json()


def main() -> None:
    """Testa OAuth e identifica o usuário dono do token."""
    print("Obtendo access token via refresh token...")

    token_data = obter_access_token()

    access_token = token_data["access_token"]
    instance_url = token_data.get("instance_url", SALESFORCE_INSTANCE_URL)
    identity_url = token_data.get("id")

    print("Access token obtido com sucesso.")
    print(f"Instance URL: {instance_url}")

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    if identity_url:
        print("\nConsultando identidade do token OAuth...")
        identidade_resp = requests.get(identity_url, headers=headers, timeout=30)

        if identidade_resp.status_code == 200:
            identidade = identidade_resp.json()

            print("\nUsuário autenticado pelo OAuth:")
            print(f"User ID: {identidade.get('user_id')}")
            print(f"Org ID: {identidade.get('organization_id')}")
            print(f"Username: {identidade.get('username')}")
            print(f"Nome: {identidade.get('display_name')}")
            print(f"Email: {identidade.get('email')}")
        else:
            print("Não foi possível consultar a identidade pelo endpoint OAuth.")
            print("Status:", identidade_resp.status_code)
            print("Resposta:", identidade_resp.text)

    sf = Salesforce(
        instance_url=instance_url,
        session_id=access_token,
        version=SALESFORCE_API_VERSION,
    )

    # Consulta somente o usuário autenticado, se o identity_url trouxe user_id.
    if identity_url:
        identidade = requests.get(identity_url, headers=headers, timeout=30).json()
        user_id = identidade.get("user_id")

        resultado = sf.query(
            f"SELECT Id, Name, Email, Username FROM User WHERE Id = '{user_id}'"
        )

        print("\nRegistro User correspondente ao token:")
        print(resultado["records"][0])


if __name__ == "__main__":
    main()