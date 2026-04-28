import logging
import warnings
from typing import Any, Optional

from langchain_ollama import ChatOllama
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

try:
    from langchain_classic.memory import ConversationBufferWindowMemory

    _MEMORIA_COM_JANELA = True
except ImportError:
    from langchain_classic.memory import ConversationBufferMemory

    _MEMORIA_COM_JANELA = False

from core.config import (
    AGENT_MAX_ITERATIONS,
    AGENT_MEMORY_WINDOW,
    AGENT_VERBOSE,
    OLLAMA_MODEL,
)
from agent.prompt import INSTRUCOES_SISTEMA
from agent.tools import LISTA_FERRAMENTAS

warnings.filterwarnings("ignore", message=".*LangChainDeprecationWarning.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

logger = logging.getLogger(__name__)


def criar_llm(modelo: str = OLLAMA_MODEL, temperature: float = 0.0) -> ChatOllama:
    """
    Cria e retorna o modelo de linguagem local via Ollama.
    """
    return ChatOllama(
        model=modelo,
        temperature=temperature,
    )


def criar_prompt() -> ChatPromptTemplate:
    """
    Monta o prompt base do agente, incluindo:
    - instruções de sistema
    - histórico da conversa
    - entrada do usuário
    - scratchpad do agente
    """
    return ChatPromptTemplate.from_messages([
        ("system", INSTRUCOES_SISTEMA),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])


def criar_memoria() -> Any:
    """
    Cria uma memória curta para reduzir reaproveitamento indevido de métricas antigas.
    """
    if _MEMORIA_COM_JANELA:
        return ConversationBufferWindowMemory(
            k=AGENT_MEMORY_WINDOW,
            memory_key="chat_history",
            return_messages=True,
        )

    return ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
    )


def criar_executor(
    usar_memoria: bool = True,
    verbose: bool = AGENT_VERBOSE,
) -> AgentExecutor:
    """
    Cria e retorna o executor do agente já configurado.
    """
    if not LISTA_FERRAMENTAS:
        raise ValueError("A LISTA_FERRAMENTAS está vazia.")

    llm = criar_llm()
    prompt_template = criar_prompt()
    memoria: Optional[Any] = criar_memoria() if usar_memoria else None

    agente_base = create_tool_calling_agent(
        llm=llm,
        tools=LISTA_FERRAMENTAS,
        prompt=prompt_template,
    )

    parametros_executor = {
        "agent": agente_base,
        "tools": LISTA_FERRAMENTAS,
        "verbose": verbose,
        "handle_parsing_errors": True,
        "max_iterations": AGENT_MAX_ITERATIONS,
        "early_stopping_method": "generate",
    }

    if memoria is not None:
        parametros_executor["memory"] = memoria

    return AgentExecutor(**parametros_executor)


def obter_executor() -> AgentExecutor:
    """
    Função pública do módulo.
    Use esta função para obter o executor pronto.
    """
    try:
        executor = criar_executor(usar_memoria=True, verbose=AGENT_VERBOSE)
        logger.info("Executor do agente inicializado com sucesso.")
        return executor
    except Exception as e:
        logger.exception("Falha ao inicializar o executor do agente.")
        raise RuntimeError(f"Erro ao inicializar o agente: {e}") from e


agente_executor = obter_executor()
