import logging
from typing import Any, Dict, List, Tuple, Optional

import requests

from core.config import PROMETHEUS_TIMEOUT_SEGUNDOS, URL_PROMETHEUS
from core.utils import media, maximo

logger = logging.getLogger(__name__)


def _resposta_erro(tipo: str, mensagem: str, detalhe: Optional[str] = None) -> Dict[str, Any]:
    """
    Padroniza o retorno de erro das consultas ao Prometheus.
    """
    resposta = {
        "resultType": "error",
        "result": [],
        "error": {
            "tipo": tipo,
            "mensagem": mensagem,
        },
    }

    if detalhe:
        resposta["error"]["detalhe"] = detalhe

    return resposta


def prom_get(caminho: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Faz uma requisição HTTP GET à API do Prometheus e retorna o campo `data`
    quando a resposta for válida.

    Em caso de falha, retorna um dicionário padronizado com erro.
    """
    url = f"{URL_PROMETHEUS}{caminho}"

    try:
        response = requests.get(url, params=params, timeout=PROMETHEUS_TIMEOUT_SEGUNDOS)
        response.raise_for_status()

        payload = response.json()

        if payload.get("status") != "success":
            logger.warning("Prometheus retornou status diferente de success: %s", payload)
            return _resposta_erro(
                tipo="erro_prometheus",
                mensagem="O Prometheus retornou uma resposta sem sucesso.",
                detalhe=str(payload),
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            logger.warning("Campo 'data' inválido na resposta do Prometheus: %s", payload)
            return _resposta_erro(
                tipo="resposta_invalida",
                mensagem="O Prometheus retornou um payload sem campo 'data' válido.",
            )

        return data

    except requests.Timeout as e:
        logger.warning("Timeout ao consultar Prometheus em %s: %s", url, e)
        return _resposta_erro(
            tipo="timeout",
            mensagem="O Prometheus não respondeu dentro do tempo limite.",
            detalhe=str(e),
        )

    except requests.ConnectionError as e:
        logger.warning("Erro de conexão ao consultar Prometheus em %s: %s", url, e)
        return _resposta_erro(
            tipo="conexao",
            mensagem="Não foi possível conectar ao Prometheus.",
            detalhe=str(e),
        )

    except requests.HTTPError as e:
        logger.warning("Erro HTTP ao consultar Prometheus em %s: %s", url, e)
        return _resposta_erro(
            tipo="http",
            mensagem="O Prometheus respondeu com erro HTTP.",
            detalhe=str(e),
        )

    except ValueError as e:
        logger.warning("Falha ao decodificar JSON do Prometheus em %s: %s", url, e)
        return _resposta_erro(
            tipo="json_invalido",
            mensagem="A resposta do Prometheus não contém JSON válido.",
            detalhe=str(e),
        )

    except requests.RequestException as e:
        logger.warning("Erro de requisição ao consultar Prometheus em %s: %s", url, e)
        return _resposta_erro(
            tipo="requisicao",
            mensagem="Falha na requisição ao Prometheus.",
            detalhe=str(e),
        )

    except Exception as e:
        logger.exception("Erro inesperado ao consultar Prometheus em %s", url)
        return _resposta_erro(
            tipo="erro_inesperado",
            mensagem="Ocorreu um erro inesperado ao consultar o Prometheus.",
            detalhe=str(e),
        )


def extrair_vector(data: Dict[str, Any]) -> List[Tuple[Dict[str, str], float]]:
    """
    Extrai resultados do tipo Vector do Prometheus.

    Retorna uma lista no formato:
    [
        (labels: dict, valor: float),
        ...
    ]
    """
    out: List[Tuple[Dict[str, str], float]] = []

    for item in data.get("result", []):
        labels = item.get("metric", {})
        val = item.get("value")

        if not val or len(val) != 2:
            continue

        try:
            out.append((labels, float(val[1])))
        except (TypeError, ValueError):
            logger.debug("Valor inválido ignorado em extrair_vector: %s", val)

    return out


def extrair_matrix(data: Dict[str, Any]) -> List[Tuple[Dict[str, str], List[Tuple[float, float]]]]:
    """
    Extrai resultados do tipo Matrix do Prometheus.

    Retorna uma lista no formato:
    [
        (labels: dict, serie: [(timestamp, valor), ...]),
        ...
    ]
    """
    out: List[Tuple[Dict[str, str], List[Tuple[float, float]]]] = []

    for item in data.get("result", []):
        labels = item.get("metric", {})
        values = item.get("values", [])
        serie: List[Tuple[float, float]] = []

        for ponto in values:
            if not isinstance(ponto, (list, tuple)) or len(ponto) != 2:
                continue

            ts, v = ponto

            try:
                serie.append((float(ts), float(v)))
            except (TypeError, ValueError):
                logger.debug("Ponto inválido ignorado em extrair_matrix: %s", ponto)

        out.append((labels, serie))

    return out


def stats_serie(serie: List[Tuple[float, float]]) -> Dict[str, Optional[float]]:
    """
    Calcula estatísticas simples de uma série temporal.

    Retorna:
    {
        "mean": média dos valores,
        "max": valor máximo
    }
    """
    valores = [v for _t, v in serie]
    return {
        "mean": media(valores),
        "max": maximo(valores),
    }
