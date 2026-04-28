# Perguntas de Monitoramento e Observabilidade

Este documento lista as perguntas de referência utilizadas para o **agente** consultar a saúde, o consumo de recursos e o estado geral da infraestrutura (Máquinas Virtuais e Containers) nos ambientes de **Site** e **Testes**.

## 1. Saúde Geral da Infraestrutura
Perguntas focadas no status de funcionamento das VMs e seus respectivos containers.

* Como está a saúde da máquina virtual do site?
* Como está a saúde da VM de testes?
* Como está a saúde dos containers da MV do site?
* Como está a saúde dos containers da MV de testes?
* *Variações de contexto:* E os containers? / Como está a saúde dos containers dele?

## 2. Consumo de Recursos (Máquinas Virtuais)
Consultas diretas sobre as métricas de hardware das instâncias.

**Ambiente: Site**
* Como está o uso de CPU da máquina do site?
* Como está o uso de memória da máquina do site?
* Como está o uso de disco da máquina do site?
* Como está o uso de rede da máquina do site?

**Ambiente: Testes**
* Como está o uso de CPU da máquina de testes?
* Como está o uso de memória da máquina de testes?
* Como está o uso de disco da máquina de testes?
* Como está o uso de rede da máquina de testes?

## 3. Análise de Containers
Perguntas para identificar gargalos, inatividade ou o status de serviços específicos.

**Métricas de Consumo**
* Quais containers mais usam CPU no site?
* Quais containers mais usam CPU em testes?
* Quais containers mais usam memória? 
  * *(Nota: Pergunta intencionalmente formulada sem o ambiente alvo [site/testes] para testar se o agente infere o contexto com base na pergunta anterior).*
* Quais containers mais usam memória em testes?

**Status e Serviços Específicos**
* Há containers inativos no site?
* Há containers inativos em testes?
* Como está o container `API` no site?
* Como está o container `Kafka` em testes?
* Como está o container `Redis` em testes?

## 4. Detecção de Anomalias e Problemas
Consultas focadas em alertas e desvios de padrão (troubleshooting).

* Há alguma anomalia na máquina do site?
* Há alguma anomalia na máquina de testes?
* Existe algum problema de rede na VM do site?
* Existe algum problema de rede na VM de testes?

## 5. Interações de Contexto
Perguntas para testar a retenção de memória de agentes conversacionais.

* E em testes? (Após uma pergunta anterior sobre o site)
* E no site? (Após uma pergunta anterior sobre testes)
* Qual ambiente você está analisando agora? (Após sequência com contexto)
