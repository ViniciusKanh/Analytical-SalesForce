"""Utilitários de data e fuso horário para o Analytical-Force.

Centraliza o tratamento de datas para o timezone configurado
(padrão ``America/Sao_Paulo``) e a conversão para os formatos usados
nas queries SOQL e na persistência (ISO 8601).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser as _dateutil_parser

# Fuso padrão do projeto. Pode ser sobrescrito nas funções.
TIMEZONE_PADRAO = "America/Sao_Paulo"


def _tz(timezone: str = TIMEZONE_PADRAO) -> ZoneInfo:
    """Retorna o objeto ZoneInfo do timezone informado, com fallback seguro."""
    try:
        return ZoneInfo(timezone)
    except Exception:
        return ZoneInfo(TIMEZONE_PADRAO)


def agora_tz(timezone: str = TIMEZONE_PADRAO) -> datetime:
    """Retorna o datetime atual com o fuso horário aplicado."""
    return datetime.now(_tz(timezone))


def parse_data(valor: str | date | datetime, timezone: str = TIMEZONE_PADRAO) -> date:
    """Converte um valor diverso em :class:`datetime.date`.

    Aceita strings ISO (ex.: ``2026-06-23``), ``date`` ou ``datetime``.

    Args:
        valor: Valor a ser convertido.
        timezone: Fuso usado para normalizar datetimes sem timezone.

    Returns:
        Objeto ``date`` correspondente.

    Raises:
        ValueError: Se o valor não puder ser interpretado como data.
    """
    if isinstance(valor, datetime):
        return valor.astimezone(_tz(timezone)).date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return _dateutil_parser.parse(valor).date()
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Data inválida: {valor!r}") from exc
    raise ValueError(f"Tipo de data não suportado: {type(valor)!r}")


def intervalo_do_dia(
    dia: date, timezone: str = TIMEZONE_PADRAO
) -> tuple[datetime, datetime]:
    """Retorna o intervalo [início, fim) de um dia com timezone aplicado.

    O fim é o início do dia seguinte, permitindo filtros do tipo
    ``data >= inicio AND data < fim``.

    Args:
        dia: Dia de referência.
        timezone: Fuso horário.

    Returns:
        Tupla ``(inicio_do_dia, inicio_do_dia_seguinte)``.
    """
    tz = _tz(timezone)
    inicio = datetime.combine(dia, time.min, tzinfo=tz)
    fim = inicio + timedelta(days=1)
    return inicio, fim


def para_soql_datetime(dt: datetime) -> str:
    """Formata um datetime para o padrão aceito em SOQL (ISO 8601 com offset).

    Exemplo de saída: ``2026-06-23T00:00:00-03:00``.

    Args:
        dt: Datetime com timezone.

    Returns:
        String formatada para uso direto em cláusulas WHERE de SOQL.
    """
    # SOQL aceita ISO 8601; isoformat já inclui o offset quando há timezone.
    return dt.isoformat(timespec="seconds")


def para_soql_date(dia: date) -> str:
    """Formata uma data para o padrão de DATE do SOQL (``YYYY-MM-DD``)."""
    return dia.isoformat()


def para_iso(dt: datetime | date) -> str:
    """Converte datetime/date para string ISO 8601 (usado na persistência)."""
    return dt.isoformat()


def formatar_data_br(dia: date) -> str:
    """Formata uma data no padrão brasileiro ``dd/mm/aaaa``."""
    return dia.strftime("%d/%m/%Y")


def datas_dos_ultimos_n_dias(referencia: date, n: int) -> list[date]:
    """Retorna a lista de datas dos ``n`` dias anteriores à referência.

    Args:
        referencia: Data de referência (não incluída na lista).
        n: Quantidade de dias anteriores.

    Returns:
        Lista de datas, da mais antiga para a mais recente.
    """
    return [referencia - timedelta(days=i) for i in range(n, 0, -1)]
