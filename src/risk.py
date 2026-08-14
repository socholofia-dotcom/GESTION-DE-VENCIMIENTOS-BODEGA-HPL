from datetime import date
import calendar


def months_until(expiration: date, today: date | None = None) -> int:
    """Meses calendario completos/aproximados hasta el vencimiento."""
    today = today or date.today()
    months = (expiration.year - today.year) * 12 + expiration.month - today.month
    if expiration.day < today.day:
        months -= 1
    return months


def risk_state(expiration: date, today: date | None = None) -> str:
    remaining = months_until(expiration, today)
    if expiration < (today or date.today()):
        return "Vencido / Retirar"
    if remaining <= 2:
        return "Crítico / Urgente"
    if remaining <= 6:
        return "Advertencia"
    return "Seguro"


def month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])

