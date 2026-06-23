"""Camada de integração com o Salesforce (somente leitura)."""

from .client import (
    SalesforceAuthError,
    SalesforceClient,
    execute_soql_query,
    get_oauth_access_token,
    get_salesforce_client,
)
from .field_mapping import FieldMapping, get_field_mapping
from .extractors import SalesforceExtractor

__all__ = [
    "SalesforceAuthError",
    "SalesforceClient",
    "execute_soql_query",
    "get_oauth_access_token",
    "get_salesforce_client",
    "FieldMapping",
    "get_field_mapping",
    "SalesforceExtractor",
]
