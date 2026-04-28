from agent.engine import agente_executor
from core.config import URL_PROMETHEUS


COMANDOS_SAIDA = {"sair", "exit", "quit"}


def exibir_banner() -> None:
    print("=====================================================")
    print("Agente Iniciado!")
    print(f"Monitorando Prometheus em: {URL_PROMETHEUS}")
    print("Digite 'sair' para encerrar.")
    print("=====================================================")


def deve_encerrar(texto: str) -> bool:
    return texto.strip().lower() in COMANDOS_SAIDA


def executar_loop() -> None:
    while True:
        try:
            pergunta = input("\nVocê: ").strip()

            if not pergunta:
                continue

            if deve_encerrar(pergunta):
                print("Encerrando o agente. Até logo!")
                break

            resposta = agente_executor.invoke({"input": pergunta})
            saida = resposta.get("output", "Não foi possível gerar uma resposta.")

            print(f"\nAgente: {saida}")

        except KeyboardInterrupt:
            print("\nEncerrando o agente. Até logo!")
            break

        except EOFError:
            print("\nEntrada encerrada. Finalizando o agente.")
            break

        except Exception as e:
            print(f"\n[Erro interno do agente] {e}")


def main() -> None:
    exibir_banner()
    executar_loop()


if __name__ == "__main__":
    main()