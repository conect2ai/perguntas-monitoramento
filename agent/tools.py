import re
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from core.config import (
    JANELA_MAXIMA_SEGUNDOS,
    JANELA_PADRAO_SEGUNDOS,
    PASSO_MAXIMO_SEGUNDOS,
    PASSO_PADRAO_SEGUNDOS,
    PROMQL_MAX_CARACTERES,
    REGEX_NOME_MAX_CARACTERES,
    resolver_alvo,
)
from services.metrics import (
    detectar_anomalias,
    executar_query_instantanea,
    executar_query_range,
    obter_saude_containers,
    obter_saude_vm,
)


FOCOS_VM = {"geral", "cpu", "memoria", "disco", "rede"}
FOCOS_CONTAINERS = {"geral", "top", "cpu", "memoria", "anomalias"}
FOCOS_ALIASES = {
    "saude": "geral",
    "saúde": "geral",
    "tudo": "geral",
    "todos": "geral",
    "mem": "memoria",
    "memória": "memoria",
    "ranking": "top",
    "principais": "top",
    "problemas": "anomalias",
    "falhas": "anomalias",
    "inativos": "anomalias",
}
TERMOS_NAO_SERVICO = {"cpu", "memoria", "memória", "disco", "rede", "ram"}


def _resposta_canonica(
    status: str,
    foco: str,
    answer: str,
    data: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
    alvo: Optional[str] = None,
    tipo: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Contrato único para ferramentas: resposta pronta, dados brutos e erros separados.
    """
    resposta: Dict[str, Any] = {
        "status": status,
        "foco": foco,
        "answer": answer,
        "data": data or {},
        "errors": errors or [],
    }

    if alvo:
        resposta["alvo"] = alvo

    if tipo:
        resposta["tipo"] = tipo

    return resposta


def _erro_alvo(detalhe: str) -> Dict[str, Any]:
    """
    Retorno padronizado para alvo ausente ou inválido.
    """
    erro = {
        "tipo": "alvo_nao_informado_ou_invalido",
        "fonte": "entrada_usuario",
        "mensagem": "Ambiente ausente ou inválido.",
        "detalhe": detalhe,
    }
    return _resposta_canonica(
        status="error",
        foco="alvo",
        answer="Qual ambiente você deseja consultar: site ou testes?",
        data={"opcoes": ["site", "testes"]},
        errors=[erro],
        tipo="alvo_nao_informado_ou_invalido",
    )


def _erro_validacao(campo: str, detalhe: str) -> Dict[str, Any]:
    """
    Retorno padronizado para parâmetros inseguros ou fora dos limites.
    """
    erro = {
        "tipo": "parametro_invalido",
        "fonte": campo,
        "mensagem": "Parâmetro inválido ou fora dos limites aceitos.",
        "detalhe": detalhe,
    }
    return _resposta_canonica(
        status="error",
        foco="validacao",
        answer=f"Parâmetro inválido: {campo}. {detalhe}",
        errors=[erro],
        tipo="parametro_invalido",
    )


def _erro_execucao(mensagem: str, detalhe: str, foco: str = "execucao") -> Dict[str, Any]:
    """
    Retorno padronizado para erros reais de execução.
    """
    erro = {
        "tipo": "erro_execucao",
        "fonte": foco,
        "mensagem": mensagem,
        "detalhe": detalhe,
    }
    return _resposta_canonica(
        status="error",
        foco=foco,
        answer=mensagem,
        errors=[erro],
        tipo="erro_execucao",
    )


def _resolver_alvo_seguro(alvo: Optional[str]) -> Dict[str, Any]:
    """
    Resolve o alvo e transforma falha em ValueError semântico.
    """
    try:
        return resolver_alvo(alvo)
    except Exception as e:
        raise ValueError(str(e)) from e


def _validar_janela(janela_segundos: int) -> int:
    try:
        janela = int(janela_segundos)
    except (TypeError, ValueError) as e:
        raise ValueError("janela_segundos deve ser um número inteiro.") from e

    if janela < 1:
        raise ValueError("janela_segundos deve ser maior ou igual a 1.")

    if janela > JANELA_MAXIMA_SEGUNDOS:
        raise ValueError(
            f"janela_segundos não pode exceder {JANELA_MAXIMA_SEGUNDOS} segundos."
        )

    return janela


def _validar_passo(passo_segundos: int, janela_segundos: int) -> int:
    try:
        passo = int(passo_segundos)
    except (TypeError, ValueError) as e:
        raise ValueError("passo_segundos deve ser um número inteiro.") from e

    if passo < 1:
        raise ValueError("passo_segundos deve ser maior ou igual a 1.")

    if passo > PASSO_MAXIMO_SEGUNDOS:
        raise ValueError(
            f"passo_segundos não pode exceder {PASSO_MAXIMO_SEGUNDOS} segundos."
        )

    if passo > janela_segundos:
        raise ValueError("passo_segundos não pode ser maior que janela_segundos.")

    return passo


def _validar_promql(promql: str) -> str:
    if not isinstance(promql, str):
        raise ValueError("promql deve ser texto.")

    consulta = promql.strip()
    if not consulta:
        raise ValueError("promql não pode estar vazio.")

    if len(consulta) > PROMQL_MAX_CARACTERES:
        raise ValueError(f"promql não pode exceder {PROMQL_MAX_CARACTERES} caracteres.")

    if any(ch in consulta for ch in [";", "\n", "\r", "\x00"]):
        raise ValueError("promql contém caracteres não permitidos para consulta crua.")

    return consulta


def _normalizar_foco(
    foco: Optional[str],
    permitidos: set[str],
    padrao: str = "geral",
) -> str:
    valor = str(foco or padrao).strip().lower()
    valor = FOCOS_ALIASES.get(valor, valor)

    if valor not in permitidos:
        opcoes = ", ".join(sorted(permitidos))
        raise ValueError(f"foco inválido '{valor}'. Opções válidas: {opcoes}.")

    return valor


def _sanitizar_regex_nome(regex_nome: str = ".*") -> str:
    """
    Aceita um nome de serviço e gera regex segura para label Prometheus.
    """
    valor = str(regex_nome or ".*").strip()

    if valor == ".*":
        return valor

    if len(valor) > REGEX_NOME_MAX_CARACTERES:
        raise ValueError(
            f"regex_nome não pode exceder {REGEX_NOME_MAX_CARACTERES} caracteres."
        )

    if valor.startswith(".*") and valor.endswith(".*") and len(valor) > 4:
        valor = valor[2:-2]

    valor = valor.strip()
    valor_normalizado = valor.lower()

    if valor_normalizado in TERMOS_NAO_SERVICO:
        raise ValueError("regex_nome deve representar um serviço/container, não uma métrica.")

    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", valor):
        raise ValueError(
            "regex_nome aceita apenas letras, números, ponto, hífen, underscore e dois-pontos."
        )

    return f".*{re.escape(valor)}.*"


def _erros_promql(resultado: Dict[str, Any], fonte: str) -> List[Dict[str, Any]]:
    erro = resultado.get("error")
    if not erro:
        return []

    return [
        {
            "tipo": erro.get("tipo", "erro_prometheus"),
            "fonte": fonte,
            "mensagem": erro.get("mensagem", "Falha ao consultar o Prometheus."),
            "detalhe": erro.get("detalhe"),
        }
    ]


def _status_por_resultado(resultado: Dict[str, Any]) -> str:
    if resultado.get("status") == "error":
        return "degraded"

    if resultado.get("coleta_status") in ("degraded", "unknown"):
        return "degraded"

    if resultado.get("errors"):
        return "degraded"

    return "success"


def _linhas_erros(errors: List[Dict[str, Any]]) -> List[str]:
    if not errors:
        return []

    linhas = ["", "Falhas/ausências de coleta:"]
    for erro in errors[:5]:
        fonte = erro.get("fonte", "desconhecida")
        tipo = erro.get("tipo", "erro")
        mensagem = erro.get("mensagem", "sem detalhe")
        linhas.append(f"- {fonte}: {mensagem} ({tipo})")

    if len(errors) > 5:
        linhas.append(f"- Mais {len(errors) - 5} erro(s) omitidos no resumo.")

    return linhas


def _linha_vm_percentual(nome: str, dados: Dict[str, Any]) -> str:
    return (
        f"{nome}: nível={dados.get('nivel', 'unknown')}, "
        f"média={dados.get('media_fmt', 'n/a')}, pico={dados.get('pico_fmt', 'n/a')}"
    )


def _linha_vm_rede(dados: Dict[str, Any]) -> str:
    return (
        f"Rede: nível={dados.get('nivel', 'unknown')}, "
        f"RX média={dados.get('rx_media_fmt', 'n/a')}, "
        f"TX média={dados.get('tx_media_fmt', 'n/a')}, "
        f"erros pico={dados.get('erros_pico_fmt', 'n/a')}"
    )


def _montar_answer_vm(resultado: Dict[str, Any], alvo: str, foco: str) -> str:
    linhas = [
        f"Máquina do {alvo}:",
        "Na VM:",
        f"Estado geral: {resultado.get('geral', 'unknown')}.",
    ]

    coleta_status = resultado.get("coleta_status", "ok")
    if coleta_status != "ok":
        linhas.append(f"Estado da coleta: {coleta_status}. Dados incompletos ou indisponíveis.")

    if foco in ("geral", "cpu"):
        linhas.append(_linha_vm_percentual("CPU", resultado.get("cpu", {})))

    if foco in ("geral", "memoria"):
        linhas.append(_linha_vm_percentual("Memória", resultado.get("memoria", {})))

    if foco in ("geral", "disco"):
        linhas.append(_linha_vm_percentual("Disco", resultado.get("disco", {})))

    if foco in ("geral", "rede"):
        linhas.append(_linha_vm_rede(resultado.get("rede", {})))

    linhas.extend(_linhas_erros(resultado.get("errors", [])))
    return "\n".join(linhas)


def _formatar_top_cpu(top_cpu: List[Dict[str, Any]], limite: int = 3) -> List[str]:
    linhas = []
    for item in top_cpu[:limite]:
        nome = item.get("nome", "desconhecido")
        valor = item.get("cpu_pico_fmt") or str(item.get("cpu_pico_cores", "n/a"))
        linhas.append(f"{nome}: {valor}")
    return linhas


def _formatar_top_memoria(top_memoria: List[Dict[str, Any]], limite: int = 3) -> List[str]:
    linhas = []
    for item in top_memoria[:limite]:
        nome = item.get("nome", "desconhecido")
        valor = item.get("mem_pico_fmt") or str(item.get("mem_pico_bytes", "n/a"))
        linhas.append(f"{nome}: {valor}")
    return linhas


def _formatar_todos_containers(detalhes: List[Dict[str, Any]]) -> List[str]:
    linhas = []
    for item in detalhes:
        nome = item.get("nome", "desconhecido")
        status = item.get("status", "unknown")
        cpu_pico = item.get("cpu_pico_fmt", "n/a")
        cpu_media = item.get("cpu_media_fmt", "n/a")
        mem_pico = item.get("mem_pico_fmt", "n/a")
        mem_media = item.get("mem_media_fmt", "n/a")

        linhas.append(
            f"{nome} | status={status} | "
            f"CPU pico={cpu_pico}, média={cpu_media} | "
            f"Memória pico={mem_pico}, média={mem_media}"
        )
    return linhas


def _formatar_cpu_containers(detalhes: List[Dict[str, Any]]) -> List[str]:
    linhas = []
    for item in detalhes:
        nome = item.get("nome", "desconhecido")
        cpu_pico = item.get("cpu_pico_fmt", "n/a")
        cpu_media = item.get("cpu_media_fmt", "n/a")
        linhas.append(f"{nome}: pico={cpu_pico}, média={cpu_media}")
    return linhas


def _formatar_memoria_containers(detalhes: List[Dict[str, Any]]) -> List[str]:
    linhas = []
    for item in detalhes:
        nome = item.get("nome", "desconhecido")
        mem_pico = item.get("mem_pico_fmt", "n/a")
        mem_media = item.get("mem_media_fmt", "n/a")
        linhas.append(f"{nome}: pico={mem_pico}, média={mem_media}")
    return linhas


def _prefixo_containers(resultado: Dict[str, Any], alvo: str) -> List[str]:
    linhas = [
        f"Máquina do {alvo}:",
        "Nos containers:",
    ]
    coleta_status = resultado.get("coleta_status", "ok")
    if coleta_status != "ok":
        linhas.append(f"Estado da coleta: {coleta_status}. Dados podem estar incompletos.")
    return linhas


def _montar_resumo_containers(resultado: Dict[str, Any], alvo: str) -> Dict[str, Any]:
    total = resultado.get("total_encontrados", 0)
    stale = resultado.get("stale", [])
    unknown = resultado.get("unknown", [])
    top_cpu = resultado.get("top_cpu", [])
    top_memoria = resultado.get("top_memoria", [])
    media_geral = resultado.get("media_geral", {})
    detalhes = resultado.get("detalhes", [])
    errors = resultado.get("errors", [])

    stale_txt = "Há containers inativos/travados." if stale else "Nenhum container inativo foi detectado."
    unknown_txt = "Há containers com estado desconhecido." if unknown else "Nenhum container com estado desconhecido foi detectado."

    top_cpu_linhas = _formatar_top_cpu(top_cpu, limite=3)
    top_memoria_linhas = _formatar_top_memoria(top_memoria, limite=3)
    todos_containers_linhas = _formatar_todos_containers(detalhes)
    cpu_containers_linhas = _formatar_cpu_containers(detalhes)
    memoria_containers_linhas = _formatar_memoria_containers(detalhes)

    cpu_media_fmt = media_geral.get("cpu_media_fmt", "n/a")
    mem_media_fmt = media_geral.get("mem_media_fmt", "n/a")

    atraso_medio = None
    atrasos = [
        c.get("atraso_segundos")
        for c in detalhes
        if c.get("atraso_segundos") is not None
    ]
    if atrasos:
        atraso_medio = sum(atrasos) / len(atrasos)

    atraso_txt = (
        f"Atraso desde a última observação: ~{atraso_medio:.2f} s"
        if atraso_medio is not None
        else "Atraso desde a última observação: n/a"
    )

    linhas_top = _prefixo_containers(resultado, alvo)
    linhas_top.extend([f"Foram encontrados {total} containers.", stale_txt, ""])
    linhas_top.append("Top CPU por pico:")
    linhas_top.extend([f"- {linha}" for linha in top_cpu_linhas] if top_cpu_linhas else ["- n/a"])
    linhas_top.extend(["", "Top memória por pico:"])
    linhas_top.extend([f"- {linha}" for linha in top_memoria_linhas] if top_memoria_linhas else ["- n/a"])
    linhas_top.extend(["", "Média geral:", f"- CPU: {cpu_media_fmt}", f"- Memória: {mem_media_fmt}"])
    if atraso_medio is not None:
        linhas_top.extend(["", atraso_txt])
    linhas_top.extend(_linhas_erros(errors))

    linhas_completas = _prefixo_containers(resultado, alvo)
    linhas_completas.extend([f"Foram encontrados {total} containers.", stale_txt, unknown_txt, ""])
    linhas_completas.append("Saúde de todos os containers:")
    linhas_completas.extend(
        [f"- {linha}" for linha in todos_containers_linhas]
        if todos_containers_linhas
        else ["- Nenhum container encontrado para o filtro informado."]
    )
    linhas_completas.extend(["", "Média geral:", f"- CPU: {cpu_media_fmt}", f"- Memória: {mem_media_fmt}"])
    if atraso_medio is not None:
        linhas_completas.extend(["", atraso_txt])
    linhas_completas.extend(_linhas_erros(errors))

    linhas_cpu = _prefixo_containers(resultado, alvo)
    linhas_cpu.append("Uso de CPU:")
    linhas_cpu.extend(
        [f"- {linha}" for linha in cpu_containers_linhas]
        if cpu_containers_linhas
        else ["- Nenhum container encontrado para o filtro informado."]
    )
    linhas_cpu.extend(["", f"Média geral de CPU: {cpu_media_fmt}"])
    linhas_cpu.extend(_linhas_erros(errors))

    linhas_memoria = _prefixo_containers(resultado, alvo)
    linhas_memoria.append("Uso de memória:")
    linhas_memoria.extend(
        [f"- {linha}" for linha in memoria_containers_linhas]
        if memoria_containers_linhas
        else ["- Nenhum container encontrado para o filtro informado."]
    )
    linhas_memoria.extend(["", f"Média geral de memória: {mem_media_fmt}"])
    linhas_memoria.extend(_linhas_erros(errors))

    linhas_anomalia = [
        f"Máquina do {alvo}:",
        "Anomalias:",
    ]
    if errors or stale or unknown:
        linhas_anomalia.append("Containers: Há anomalias ou incertezas detectadas.")
        linhas_anomalia.append(stale_txt)
        linhas_anomalia.append(unknown_txt)
    else:
        linhas_anomalia.append("Containers: Nenhuma anomalia detectada.")
    linhas_anomalia.extend(_linhas_erros(errors))

    return {
        "resumo_estruturado_top": {
            "total": total,
            "stale": stale,
            "unknown": unknown,
            "top_cpu_pico": top_cpu_linhas,
            "top_memoria_pico": top_memoria_linhas,
            "media_geral": {"cpu": cpu_media_fmt, "memoria": mem_media_fmt},
            "atraso_ultima_observacao": atraso_txt,
        },
        "resumo_estruturado_completo": {
            "total": total,
            "stale": stale,
            "unknown": unknown,
            "containers": todos_containers_linhas,
            "media_geral": {"cpu": cpu_media_fmt, "memoria": mem_media_fmt},
            "atraso_ultima_observacao": atraso_txt,
        },
        "resumo_texto_top": "\n".join(linhas_top),
        "resumo_texto_completo": "\n".join(linhas_completas),
        "resumo_cpu_texto": "\n".join(linhas_cpu),
        "resumo_memoria_texto": "\n".join(linhas_memoria),
        "resumo_anomalia_texto": "\n".join(linhas_anomalia),
    }


def _montar_answer_anomalias(resultado: Dict[str, Any], alvo: str) -> str:
    linhas = [
        f"Máquina do {alvo}:",
        "Anomalias:",
    ]

    if resultado.get("status") == "degraded":
        linhas.append("Estado da coleta: degraded. Dados incompletos ou indisponíveis.")

    anomalias = resultado.get("anomalias", [])
    if not anomalias:
        linhas.append("Nenhuma anomalia detectada.")
    else:
        for item in anomalias:
            tipo = item.get("tipo", "desconhecida")
            nivel = item.get("nivel", "unknown")
            linha = f"- {tipo}: nível={nivel}"

            if item.get("media") or item.get("pico"):
                linha += f", média={item.get('media', 'n/a')}, pico={item.get('pico', 'n/a')}"

            if item.get("erros"):
                linha += f", erros={item.get('erros')}"

            if item.get("lista"):
                nomes = [str(c.get("nome", c)) for c in item["lista"][:5]]
                linha += f", itens={', '.join(nomes)}"

            linhas.append(linha)

    linhas.extend(_linhas_erros(resultado.get("errors", [])))
    return "\n".join(linhas)


def _montar_answer_promql(resultado: Dict[str, Any], foco: str) -> str:
    linhas = ["Consulta PromQL:"]
    errors = _erros_promql(resultado, foco)

    if errors:
        linhas.append("Estado da coleta: degraded.")
        linhas.extend(_linhas_erros(errors))
        return "\n".join(linhas)

    linhas.append("Estado da coleta: success.")
    linhas.append(f"resultType={resultado.get('resultType', 'n/a')}")
    linhas.append(f"séries retornadas={len(resultado.get('result', []))}")
    return "\n".join(linhas)


@tool
def prom_consulta_instantanea(promql: str) -> Dict[str, Any]:
    """
    Consulta instantânea no Prometheus (/api/v1/query).
    Use somente quando o usuário pedir PromQL ou métricas cruas explicitamente.
    """
    try:
        consulta = _validar_promql(promql)
        resultado = executar_query_instantanea(consulta)
        errors = _erros_promql(resultado, "promql_instantanea")
        status = "degraded" if errors else "success"
        return _resposta_canonica(
            status=status,
            foco="promql_instantanea",
            answer=_montar_answer_promql(resultado, "promql_instantanea"),
            data=resultado,
            errors=errors,
        )
    except ValueError as e:
        return _erro_validacao("promql", str(e))
    except Exception as e:
        return _erro_execucao(
            mensagem="Falha ao executar consulta instantânea no Prometheus.",
            detalhe=str(e),
            foco="promql_instantanea",
        )


@tool
def prom_consulta_range(
    promql: str,
    janela_segundos: int = JANELA_PADRAO_SEGUNDOS,
    passo_segundos: int = PASSO_PADRAO_SEGUNDOS,
) -> Dict[str, Any]:
    """
    Consulta por intervalo no Prometheus (/api/v1/query_range).
    Use somente quando o usuário pedir PromQL ou métricas cruas explicitamente.
    """
    try:
        consulta = _validar_promql(promql)
        janela = _validar_janela(janela_segundos)
        passo = _validar_passo(passo_segundos, janela)
        resultado = executar_query_range(consulta, janela, passo)
        errors = _erros_promql(resultado, "promql_range")
        status = "degraded" if errors else "success"
        return _resposta_canonica(
            status=status,
            foco="promql_range",
            answer=_montar_answer_promql(resultado, "promql_range"),
            data=resultado,
            errors=errors,
        )
    except ValueError as e:
        return _erro_validacao("promql_range", str(e))
    except Exception as e:
        return _erro_execucao(
            mensagem="Falha ao executar consulta por intervalo no Prometheus.",
            detalhe=str(e),
            foco="promql_range",
        )


@tool
def tool_obter_saude_vm(
    alvo: Optional[str] = None,
    janela_segundos: int = JANELA_PADRAO_SEGUNDOS,
    foco: str = "geral",
) -> Dict[str, Any]:
    """
    Retorna resposta pronta e dados de saúde da VM.

    Parâmetros:
    - alvo: site ou testes.
    - foco: geral, cpu, memoria, disco ou rede.
    """
    try:
        cfg = _resolver_alvo_seguro(alvo)
        janela = _validar_janela(janela_segundos)
        foco_normalizado = _normalizar_foco(foco, FOCOS_VM)
        resultado = obter_saude_vm(
            janela_segundos=janela,
            job_node=cfg["job_node"],
        )
        resultado["alvo"] = cfg["alvo"]

        return _resposta_canonica(
            status=_status_por_resultado(resultado),
            alvo=cfg["alvo"],
            foco=f"vm_{foco_normalizado}",
            answer=_montar_answer_vm(resultado, cfg["alvo"], foco_normalizado),
            data=resultado,
            errors=resultado.get("errors", []),
        )
    except ValueError as e:
        detalhe = str(e)
        if "Ambiente" in detalhe or "Alvo" in detalhe:
            return _erro_alvo(detalhe)
        return _erro_validacao("tool_obter_saude_vm", detalhe)
    except Exception as e:
        return _erro_execucao(
            mensagem="Falha ao obter a saúde da VM.",
            detalhe=str(e),
            foco="vm",
        )


@tool
def tool_obter_saude_containers(
    alvo: Optional[str] = None,
    janela_segundos: int = JANELA_PADRAO_SEGUNDOS,
    regex_nome: str = ".*",
    foco: str = "geral",
) -> Dict[str, Any]:
    """
    Retorna resposta pronta e dados de saúde dos containers.

    Parâmetros:
    - alvo: site ou testes.
    - regex_nome: use ".*" para todos ou um nome simples de serviço/container.
    - foco: geral, top, cpu, memoria ou anomalias.
    """
    try:
        cfg = _resolver_alvo_seguro(alvo)
        janela = _validar_janela(janela_segundos)
        regex_seguro = _sanitizar_regex_nome(regex_nome)
        foco_normalizado = _normalizar_foco(foco, FOCOS_CONTAINERS)

        resultado = obter_saude_containers(
            janela_segundos=janela,
            job_containers=cfg["job_containers"],
            regex_nome=regex_seguro,
        )

        resumo = _montar_resumo_containers(resultado, cfg["alvo"])
        resultado["alvo"] = cfg["alvo"]
        resultado["regex_nome"] = regex_seguro
        resultado.update(resumo)

        chave_answer = {
            "geral": "resumo_texto_completo",
            "top": "resumo_texto_top",
            "cpu": "resumo_cpu_texto",
            "memoria": "resumo_memoria_texto",
            "anomalias": "resumo_anomalia_texto",
        }[foco_normalizado]

        return _resposta_canonica(
            status=_status_por_resultado(resultado),
            alvo=cfg["alvo"],
            foco=f"containers_{foco_normalizado}",
            answer=resultado[chave_answer],
            data=resultado,
            errors=resultado.get("errors", []),
        )
    except ValueError as e:
        detalhe = str(e)
        if "Ambiente" in detalhe or "Alvo" in detalhe:
            return _erro_alvo(detalhe)
        return _erro_validacao("tool_obter_saude_containers", detalhe)
    except Exception as e:
        return _erro_execucao(
            mensagem="Falha ao obter a saúde dos containers.",
            detalhe=str(e),
            foco="containers",
        )


@tool
def tool_detectar_anomalias(
    alvo: Optional[str] = None,
    janela_segundos: int = JANELA_PADRAO_SEGUNDOS,
) -> Dict[str, Any]:
    """
    Checa anomalias na VM e nos containers para um alvo.
    """
    try:
        cfg = _resolver_alvo_seguro(alvo)
        janela = _validar_janela(janela_segundos)
        resultado = detectar_anomalias(
            janela_segundos=janela,
            job_node=cfg["job_node"],
            job_containers=cfg["job_containers"],
        )
        resultado["alvo"] = cfg["alvo"]

        return _resposta_canonica(
            status=resultado.get("status", _status_por_resultado(resultado)),
            alvo=cfg["alvo"],
            foco="anomalias",
            answer=_montar_answer_anomalias(resultado, cfg["alvo"]),
            data=resultado,
            errors=resultado.get("errors", []),
        )
    except ValueError as e:
        detalhe = str(e)
        if "Ambiente" in detalhe or "Alvo" in detalhe:
            return _erro_alvo(detalhe)
        return _erro_validacao("tool_detectar_anomalias", detalhe)
    except Exception as e:
        return _erro_execucao(
            mensagem="Falha ao detectar anomalias no ambiente.",
            detalhe=str(e),
            foco="anomalias",
        )


LISTA_FERRAMENTAS = [
    tool_obter_saude_vm,
    tool_obter_saude_containers,
    tool_detectar_anomalias,
    prom_consulta_instantanea,
    prom_consulta_range,
]
