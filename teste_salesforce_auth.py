from dotenv import load_dotenv
from simple_salesforce import Salesforce
import os

# Carrega variáveis do arquivo .env
load_dotenv()

username = os.getenv("SALESFORCE_USERNAME")
password = os.getenv("SALESFORCE_PASSWORD")
security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
domain = os.getenv("SALESFORCE_DOMAIN", "login")

print("Testando autenticação Salesforce...")
print(f"Usuário carregado: {username}")
print(f"Senha carregada: {'sim' if password else 'não'}")
print(f"Token carregado: {'sim' if security_token else 'não'}")
print(f"Domínio: {domain}")
print("API Version: 64.0")

sf = Salesforce(
    username=username,
    password=password,
    security_token=security_token,
    domain=domain,
    version="64.0"
)

resultado = sf.query("SELECT Id, Name FROM User LIMIT 1")

print("Autenticação realizada com sucesso.")
print(resultado["records"][0]["Id"], resultado["records"][0]["Name"])