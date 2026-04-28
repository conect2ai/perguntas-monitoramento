import math
from typing import Iterable, Optional


def _valor_invalido(valor: Optional[float]) -> bool:
    """
    Retorna True quando o valor é None ou NaN.
    """
    return valor is None or math.isnan(valor)


def _filtrar_validos(valores: Iterable[Optional[float]]) -> list[float]:
    """
    Remove valores None e NaN de um iterável numérico.
    """
    return [float(v) for v in valores if not _valor_invalido(v)]


def formatar_bytes(valor: Optional[float]) -> str:
    """
    Converte bytes para formato legível por humanos.
    Exemplo: 1048576 -> '1.00 MB'
    """
    if _valor_invalido(valor):
        return "n/a"

    unidades = ["B", "KB", "MB", "GB", "TB", "PB"]
    v = float(valor)
    i = 0

    while v >= 1024 and i < len(unidades) - 1:
        v /= 1024
        i += 1

    return f"{v:.2f} {unidades[i]}"


def formatar_bps(bytes_por_seg: Optional[float]) -> str:
    """
    Converte bytes por segundo para formato legível.
    Exemplo: 1048576 -> '1.00 MB/s'
    """
    if _valor_invalido(bytes_por_seg):
        return "n/a"

    return f"{formatar_bytes(bytes_por_seg)}/s"


def formatar_pct(pct: Optional[float]) -> str:
    """
    Formata porcentagem com uma casa decimal.
    Exemplo: 3.75555 -> '3.8%'
    """
    if _valor_invalido(pct):
        return "n/a"

    return f"{pct:.1f}%"


def nivel_por_limiar(valor: Optional[float], aviso: float, critico: float) -> str:
    """
    Classifica um valor conforme os limiares informados.
    Retorna: unknown, ok, warning ou critical.
    """
    if _valor_invalido(valor):
        return "unknown"

    if valor >= critico:
        return "critical"

    if valor >= aviso:
        return "warning"

    return "ok"


def media(valores: Iterable[Optional[float]]) -> Optional[float]:
    """
    Calcula a média ignorando valores None e NaN.
    """
    valores_validos = _filtrar_validos(valores)
    return sum(valores_validos) / len(valores_validos) if valores_validos else None


def maximo(valores: Iterable[Optional[float]]) -> Optional[float]:
    """
    Retorna o maior valor ignorando None e NaN.
    """
    valores_validos = _filtrar_validos(valores)
    return max(valores_validos) if valores_validos else None