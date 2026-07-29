"""
================================================================================
 AGENT CONCEPTS DEMO — Certificação Claude Developer (com chamadas REAIS à API)
================================================================================
Aplicação didática que exemplifica, na prática, os conceitos do artigo
"Building a production agent: the loop, wiring paths, orchestration, and
human-in-the-loop", usando chamadas reais ao modelo Claude via Anthropic API.

CONFIGURAÇÃO:
  1. pip install anthropic python-dotenv
  2. Crie um arquivo ".env" na mesma pasta deste script com o conteúdo:
         ANTHROPIC_API_KEY=sk-ant-...sua-chave...
  3. Rode: python3 agent_concepts_demo.py

Seções marcadas com 🟢 fazem chamadas REAIS à API (precisam da chave).
Seções marcadas com ⚪ são deliberadamente SIMULADAS/lógicas, porque
representam decisões de código (não de modelo) ou recursos de API que
exigem uma configuração/beta específica (ex.: Managed Agents).

Se a ANTHROPIC_API_KEY não for encontrada, o script avisa claramente
em cada seção 🟢 e não tenta chamar a API.
================================================================================
"""

import os
import sys
import json
import time
import textwrap
from typing import Callable

# ------------------------------------------------------------------------
# Carregamento do .env
# ------------------------------------------------------------------------

def carregar_dotenv():
    """Carrega variáveis do arquivo .env. Usa python-dotenv se disponível,
    senão faz um parser manual simples como fallback."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return "python-dotenv"
    except ImportError:
        pass

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, _, valor = linha.partition("=")
                chave = chave.strip()
                valor = valor.strip().strip('"').strip("'")
                os.environ.setdefault(chave, valor)
        return "parser manual (.env)"
    return None


_MODO_ENV = carregar_dotenv()

# ------------------------------------------------------------------------
# Cliente Anthropic
# ------------------------------------------------------------------------

MODEL_NAME = "claude-sonnet-5"

client = None
LIVE_MODE = False
_MOTIVO_SEM_LIVE = None

try:
    from anthropic import Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _MOTIVO_SEM_LIVE = "ANTHROPIC_API_KEY não encontrada (verifique seu arquivo .env)"
    else:
        client = Anthropic(api_key=api_key)
        LIVE_MODE = True
except ImportError:
    _MOTIVO_SEM_LIVE = "lib 'anthropic' não instalada -> rode: pip install anthropic"


# ------------------------------------------------------------------------
# Utilitários de exibição
# ------------------------------------------------------------------------

def header(titulo: str):
    print("\n" + "=" * 78)
    print(f" {titulo}")
    print("=" * 78)


def subheader(titulo: str):
    print("\n" + "-" * 78)
    print(f" {titulo}")
    print("-" * 78)


def explica(texto: str):
    print(textwrap.fill(texto, width=78))


def pausa():
    input("\n[Enter para voltar ao menu]")


def aviso_sem_live():
    print("[AVISO] Esta seção faz chamadas REAIS à API e requer uma chave válida.")
    if _MOTIVO_SEM_LIVE:
        print(f"        Motivo: {_MOTIVO_SEM_LIVE}")
    print("        Configure o arquivo .env com ANTHROPIC_API_KEY=sk-ant-... e tente novamente.")


# ------------------------------------------------------------------------
# Helpers de chamada real à API (Messages API)
# ------------------------------------------------------------------------

def uma_chamada(system_prompt: str, user_message: str, tools: list | None = None):
    """Faz UMA chamada real (sem loop) e imprime o que o modelo retornou."""
    try:
        kwargs = dict(model=MODEL_NAME, max_tokens=1024, system=system_prompt,
                       messages=[{"role": "user", "content": user_message}])
        if tools:
            kwargs["tools"] = tools
        resposta = client.messages.create(**kwargs)
    except Exception as e:
        print(f"[ERRO na chamada à API] {e}")
        return None

    for bloco in resposta.content:
        if bloco.type == "text":
            print(f"[Claude - texto] {bloco.text}")
        elif bloco.type == "tool_use":
            print(f"[Claude - tool_use] chamaria '{bloco.name}' com input {bloco.input}")
    return resposta


def agent_loop(system_prompt: str, user_message: str, tools: list,
                executores: dict[str, Callable], max_turns: int = 5,
                hitl_tools: set | None = None):
    """
    Loop de agente REAL e genérico, reaproveitado por várias demos.
    - system_prompt / user_message: entrada inicial
    - tools: schemas das ferramentas registradas
    - executores: {nome_da_ferramenta: função python que a executa de fato}
    - max_turns: condição de saída por limite (passo 4 do artigo)
    - hitl_tools: nomes de ferramentas que exigem aprovação humana (HITL)
    """
    if not LIVE_MODE:
        aviso_sem_live()
        return

    hitl_tools = hitl_tools or set()
    messages = [{"role": "user", "content": user_message}]
    print(f"[SEU CÓDIGO] system prompt: \"{system_prompt}\"")
    print(f"[SEU CÓDIGO] mensagem do usuário: \"{user_message}\"")

    for turno in range(1, max_turns + 1):
        subheader(f"Turno {turno}")
        try:
            resposta = client.messages.create(
                model=MODEL_NAME, max_tokens=1024,
                system=system_prompt, tools=tools, messages=messages,
            )
        except Exception as e:
            print(f"[ERRO na chamada à API] {e}")
            return

        blocos = resposta.content
        tool_use_blocks = [b for b in blocos if b.type == "tool_use"]
        text_blocks = [b for b in blocos if b.type == "text"]

        for tb in text_blocks:
            print(f"[Claude] {tb.text}")

        if not tool_use_blocks:
            print("\n[SEU CÓDIGO] Nenhum tool_use neste turno -> condição de saída "
                  "atingida (resposta final do modelo).")
            return

        assistant_content = []
        for b in blocos:
            if b.type == "text":
                assistant_content.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                assistant_content.append(
                    {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                )
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for b in tool_use_blocks:
            if b.name in hitl_tools:
                print(f"\n[SISTEMA] '{b.name}' requer aprovação humana (HITL) "
                      f"antes de executar. Input: {b.input}")
                resp = input("Aprovar execução? (s/n): ").strip().lower()
                if resp != "s":
                    print("[SEU CÓDIGO] Execução NEGADA pelo humano.")
                    resultado = {"status": "rejeitado_pelo_humano"}
                    tool_results.append({"type": "tool_result", "tool_use_id": b.id,
                                          "content": json.dumps(resultado, ensure_ascii=False)})
                    continue
            fn = executores.get(b.name)
            resultado = fn(**b.input) if fn else {"erro": f"ferramenta '{b.name}' não implementada"}
            print(f"   [SEU CÓDIGO] executou '{b.name}'({b.input}) -> {resultado}")
            tool_results.append({"type": "tool_result", "tool_use_id": b.id,
                                  "content": json.dumps(resultado, ensure_ascii=False)})

        messages.append({"role": "user", "content": tool_results})

    print(f"\n[SEU CÓDIGO] max_turns={max_turns} atingido -> condição de saída "
          f"por LIMITE (evita loop infinito, mesmo sem o modelo 'se oferecer' para parar).")


# ==========================================================================
# 1) WORKFLOW vs AGENTE
# ==========================================================================

def demo_workflow():
    header("1a) WORKFLOW — passos fixos, sequência sempre igual  ⚪ (lógica pura, sem modelo)")
    explica(
        "Cenário: aprovar um reembolso de despesa. Todos os passos e a ordem "
        "são conhecidos de antemão -> isso é um WORKFLOW, não precisa de agente "
        "nem de chamada ao modelo."
    )
    passos = [
        "1. Validar campos obrigatórios do formulário",
        "2. Verificar se o valor está dentro da política (<= R$500 = auto-aprovação)",
        "3. Se acima do limite, encaminhar para aprovação humana",
        "4. Registrar decisão no sistema financeiro",
    ]
    valor = 320.00
    for p in passos:
        print(p)
    print()
    if valor <= 500:
        print(f"-> Valor R${valor:.2f} dentro da política. Auto-aprovado. FIM.")
    else:
        print(f"-> Valor R${valor:.2f} acima da política. Encaminhado para humano. FIM.")
    explica(
        "\nObserve: o CÓDIGO decide o caminho (if/else), não o modelo. Nenhuma "
        "chamada à API é necessária aqui — e é exatamente esse o ponto do workflow."
    )


def demo_agent():
    header("1b) AGENTE — objetivo definido, caminho decidido pelo modelo  🟢 (chamada real)")
    explica(
        "Cenário: 'Descubra por que o pedido #4821 está atrasado e resolva.' "
        "O modelo decide, em tempo real, quais ferramentas chamar e em que ordem."
    )
    if not LIVE_MODE:
        aviso_sem_live()
        return

    tools = [
        {"name": "consultar_pedido", "description": "Consulta o status logístico de um pedido.",
         "input_schema": {"type": "object", "properties": {
             "pedido_id": {"type": "integer"}}, "required": ["pedido_id"]}},
        {"name": "consultar_transportadora", "description": "Consulta a transportadora responsável pelo pedido.",
         "input_schema": {"type": "object", "properties": {
             "pedido_id": {"type": "integer"}}, "required": ["pedido_id"]}},
        {"name": "reenviar_notificacao", "description": "Reenvia uma notificação ao cliente sobre o pedido.",
         "input_schema": {"type": "object", "properties": {
             "pedido_id": {"type": "integer"}, "motivo": {"type": "string"}},
             "required": ["pedido_id", "motivo"]}},
    ]

    def consultar_pedido(pedido_id):
        return {"pedido_id": pedido_id, "status": "sem atualização há 6 dias",
                "centro_distribuicao": "SP"}

    def consultar_transportadora(pedido_id):
        return {"pedido_id": pedido_id, "status_transporte": "pacote extraviado em trânsito"}

    def reenviar_notificacao(pedido_id, motivo):
        return {"pedido_id": pedido_id, "notificacao": "enviada", "motivo": motivo}

    executores = {
        "consultar_pedido": consultar_pedido,
        "consultar_transportadora": consultar_transportadora,
        "reenviar_notificacao": reenviar_notificacao,
    }

    agent_loop(
        system_prompt="Você é um agente de logística. Investigue o atraso do pedido "
                      "usando as ferramentas disponíveis e tome uma ação corretiva.",
        user_message="Descubra por que o pedido #4821 está atrasado e resolva.",
        tools=tools, executores=executores, max_turns=5,
    )


def menu_workflow_vs_agent():
    while True:
        header("TÓPICO 1: Workflow ou Agente?")
        print("1. WORKFLOW (passos fixos)                     ⚪")
        print("2. AGENTE (caminho decidido pelo modelo)         🟢")
        print("0. Voltar")
        escolha = input("\nEscolha: ").strip()
        if escolha == "1":
            demo_workflow(); pausa()
        elif escolha == "2":
            demo_agent(); pausa()
        elif escolha == "0":
            return
        else:
            print("Opção inválida.")


# ==========================================================================
# 2) TRÊS CAMINHOS DE WIRING
# ==========================================================================

def demo_raw_loop():
    header("2a) RAW MESSAGES API LOOP — você escreve tudo  🟢 (chamada real)")
    explica(
        "Você mesmo envia a requisição, lê os blocos tool_use, executa a "
        "ferramenta e devolve o tool_result. Controle total, responsabilidade total."
    )
    if not LIVE_MODE:
        aviso_sem_live()
        return

    def executar_ferramenta(sku):
        return {"sku": sku, "quantidade": 12}

    tools = [{
        "name": "consultar_estoque",
        "description": "Consulta a quantidade em estoque de um SKU.",
        "input_schema": {"type": "object", "properties": {"sku": {"type": "string"}},
                          "required": ["sku"]},
    }]
    system_prompt = "Você verifica estoque de produtos antes de confirmar um pedido."
    messages = [{"role": "user", "content": "Tem estoque do SKU 'CAM-042'?"}]

    print("\n[SEU CÓDIGO] Passo 1: envia mensagem inicial ao modelo (chamada real)")
    try:
        resposta = client.messages.create(model=MODEL_NAME, max_tokens=1024,
                                           system=system_prompt, tools=tools, messages=messages)
    except Exception as e:
        print(f"[ERRO na chamada à API] {e}")
        return

    tool_blocks = [b for b in resposta.content if b.type == "tool_use"]
    print(f"[SEU CÓDIGO] Passo 2: identifica {len(tool_blocks)} tool_use block(s)")

    if not tool_blocks:
        texto = "".join(b.text for b in resposta.content if b.type == "text")
        print(f"[Claude respondeu direto, sem ferramenta] {texto}")
        return

    assistant_content = [{"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                          for b in tool_blocks]
    tool_results = []
    for b in tool_blocks:
        print(f"[SEU CÓDIGO] Passo 3: executa '{b.name}' com input {b.input}")
        resultado = executar_ferramenta(**b.input)
        tool_results.append({"type": "tool_result", "tool_use_id": b.id,
                              "content": json.dumps(resultado, ensure_ascii=False)})
        print(f"[SEU CÓDIGO] Passo 4: obteve resultado {resultado}")

    messages.append({"role": "assistant", "content": assistant_content})
    messages.append({"role": "user", "content": tool_results})
    print("[SEU CÓDIGO] Passo 5: acrescenta tool_result e reenvia ao modelo (chamada real)")

    try:
        resposta_final = client.messages.create(model=MODEL_NAME, max_tokens=1024,
                                                  system=system_prompt, tools=tools, messages=messages)
    except Exception as e:
        print(f"[ERRO na chamada à API] {e}")
        return

    texto_final = "".join(b.text for b in resposta_final.content if b.type == "text")
    print(f"[SEU CÓDIGO] Passo 6: resposta final ao usuário -> \"{texto_final}\"")
    explica(
        "\nNada disso veio de graça: gerenciamento de contexto, retries e "
        "condição de saída são todos escritos e testados por você."
    )


class MiniAgentSDK:
    """
    Simula uma Agent SDK simplificada: registra ferramentas e system prompt,
    e o método .run() cuida da ITERAÇÃO do loop REAL contra a API, mas a
    EXECUÇÃO da ferramenta continua sendo responsabilidade do código do
    desenvolvedor (exatamente como descrito no artigo).
    """

    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.tools_schema = []
        self.executores = {}

    def register_tool(self, name: str, description: str, input_schema: dict, fn: Callable):
        self.tools_schema.append({"name": name, "description": description, "input_schema": input_schema})
        self.executores[name] = fn
        print(f"[SDK] Ferramenta registrada: {name}")

    def run(self, user_message: str, max_turns: int = 4):
        print(f"[SDK] Iniciando loop REAL. System prompt: \"{self.system_prompt}\"")
        agent_loop(self.system_prompt, user_message, self.tools_schema,
                   self.executores, max_turns=max_turns)
        print("[SDK] Loop encerrado automaticamente pela SDK (você não escreveu a iteração).")


def demo_agent_sdk():
    header("2b) AGENT SDK — a SDK cuida da iteração, você cuida da execução  🟢 (chamada real)")
    explica(
        "Você registra ferramentas e o system prompt; a 'SDK' (aqui, uma classe "
        "de exemplo) gerencia o loop real contra a API. Seu código só executa a "
        "ferramenta de fato."
    )
    if not LIVE_MODE:
        aviso_sem_live()
        return

    sdk = MiniAgentSDK(system_prompt="Você agenda reuniões respeitando a agenda da pessoa.")
    sdk.register_tool(
        "checar_agenda", "Verifica o horário livre de uma pessoa.",
        {"type": "object", "properties": {"pessoa": {"type": "string"}}, "required": ["pessoa"]},
        lambda pessoa: {"pessoa": pessoa, "livre_as": "15:00"},
    )
    sdk.run("Agende uma reunião com a Maria hoje.", max_turns=3)


def demo_managed_agents():
    header("2c) CLAUDE MANAGED AGENTS  ⚪ (simulado — recurso beta com API própria)")
    explica(
        "Managed Agents é um recurso em beta pública que usa uma superfície de API "
        "diferente da Messages API padrão (definição do agente como recurso versionado "
        "+ streaming de eventos via SSE). Por isso esta seção permanece SIMULADA aqui: "
        "o objetivo é ilustrar o CONCEITO (você não escreve a iteração, a Anthropic roda "
        "o loop e o sandbox), sem depender de uma configuração de beta específica."
    )

    agent_definition = {
        "id": "agent_reembolsos_v3",
        "model": MODEL_NAME,
        "system_prompt": "Você processa solicitações de reembolso de longa duração.",
        "tools": ["consultar_erp", "emitir_estorno"],
    }
    print(f"[APP] Agente definido como recurso de API: "
          f"{json.dumps(agent_definition, indent=2, ensure_ascii=False)}")

    print("\n[APP] Enviando evento do usuário para o agente gerenciado...")
    eventos_simulados_sse = [
        {"event": "tool_call", "data": {"name": "consultar_erp", "input": {"pedido": 991}}},
        {"event": "tool_result", "data": {"status": "pedido elegível para estorno"}},
        {"event": "tool_call", "data": {"name": "emitir_estorno", "input": {"pedido": 991, "valor": 149.90}}},
        {"event": "tool_result", "data": {"status": "estorno emitido"}},
        {"event": "done", "data": {"summary": "Reembolso do pedido 991 concluído em 47 minutos."}},
    ]
    for evento in eventos_simulados_sse:
        print(f"[STREAM SSE recebido] {evento['event']}: {evento['data']}")

    explica(
        "\nRepare: você NUNCA escreveria 'enquanto houver tool_use, execute'. "
        "A Anthropic roda o loop, o sandbox e as retries; sua aplicação só "
        "consome eventos. Ótimo para tarefas longas, mas atenção: sessões ficam "
        "armazenadas no servidor -> NÃO elegível para ZDR nem BAA HIPAA."
    )


def menu_wiring_paths():
    while True:
        header("TÓPICO 2: Caminhos de Wiring (implementação do loop)")
        print("1. Raw Messages API Loop                         🟢")
        print("2. Agent SDK                                     🟢")
        print("3. Claude Managed Agents                         ⚪")
        print("0. Voltar")
        escolha = input("\nEscolha: ").strip()
        if escolha == "1":
            demo_raw_loop(); pausa()
        elif escolha == "2":
            demo_agent_sdk(); pausa()
        elif escolha == "3":
            demo_managed_agents(); pausa()
        elif escolha == "0":
            return
        else:
            print("Opção inválida.")


# ==========================================================================
# 3) OS QUATRO PASSOS DO LOOP
# ==========================================================================

def demo_register_tools():
    header("3a) Registrar ferramentas  ⚪ (validação de schema, lógica pura)")
    explica("Cada ferramenta segue o mesmo formato de schema. O modelo só 'enxerga' o que foi registrado.")
    tools = [{
        "name": "consultar_clima",
        "description": "Retorna a previsão do tempo para uma cidade.",
        "input_schema": {"type": "object", "properties": {"cidade": {"type": "string"}},
                          "required": ["cidade"]},
    }]
    for t in tools:
        print(json.dumps(t, indent=2, ensure_ascii=False))

    print("\nChecagem: o system prompt referencia 'consultar_clima'? Vamos validar:")
    nomes_registrados = {t["name"] for t in tools}
    nomes_no_prompt = {"consultar_clima"}  # extraído de forma simplificada, só p/ demo
    faltando = nomes_no_prompt - nomes_registrados
    sobrando = nomes_registrados - nomes_no_prompt
    if not faltando and not sobrando:
        print("OK: todas as ferramentas citadas no prompt estão registradas, e vice-versa.")
    else:
        print(f"PROBLEMA -> citadas mas não registradas: {faltando} | registradas mas não usadas: {sobrando}")


def demo_system_prompt_scope():
    header("3b) Escopo do system prompt  🟢 (duas chamadas reais, para comparar)")
    explica("Mesma tarefa, mesmas ferramentas -- só o system prompt muda entre um prompt "
            "amplo e um escopado à tarefa.")
    if not LIVE_MODE:
        aviso_sem_live()
        return

    tools = [
        {"name": "cancelar_assinatura", "description": "Cancela a assinatura do usuário.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "consultar_status_assinatura", "description": "Consulta o status da assinatura.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
    ]
    pedido = "Cancele minha assinatura e também me recomende um filme para assistir hoje."

    subheader("Com prompt AMPLO")
    uma_chamada(
        system_prompt="Você é um assistente útil e pode ajudar com qualquer coisa.",
        user_message=pedido, tools=tools,
    )

    subheader("Com prompt ESCOPADO")
    uma_chamada(
        system_prompt="Sua única tarefa é gerenciar assinaturas. Ferramentas disponíveis: "
                      "cancelar_assinatura, consultar_status_assinatura. Não responda a "
                      "pedidos fora desse escopo; apenas informe educadamente que não pode ajudar com eles.",
        user_message=pedido, tools=tools,
    )
    explica("\nCompare as duas respostas acima: o prompt escopado tende a produzir "
            "roteamento de ferramenta mais previsível e recusa educadamente o que está fora do escopo.")


def demo_tool_use_loop():
    header("3c) Lidar com múltiplos tool_use no mesmo turno  🟢 (chamada real)")
    explica("Pedimos explicitamente duas consultas independentes -- o modelo pode "
            "pedir as duas ferramentas no MESMO turno, e ambas devem ser resolvidas "
            "antes do próximo turno.")
    if not LIVE_MODE:
        aviso_sem_live()
        return

    tools = [
        {"name": "consultar_preco", "description": "Consulta o preço de um item.",
         "input_schema": {"type": "object", "properties": {"item": {"type": "string"}},
                           "required": ["item"]}},
        {"name": "consultar_frete", "description": "Consulta o valor do frete para um CEP.",
         "input_schema": {"type": "object", "properties": {"cep": {"type": "string"}},
                           "required": ["cep"]}},
    ]

    def consultar_preco(item):
        return {"item": item, "preco": 89.90}

    def consultar_frete(cep):
        return {"cep": cep, "frete": 14.50}

    agent_loop(
        system_prompt="Você ajuda o cliente a decidir uma compra. Use as ferramentas "
                      "necessárias para responder com preço total (produto + frete).",
        user_message="Quero comprar um mouse e entregar no CEP 01310-000. Consulte o "
                     "preço do mouse e o frete para esse CEP.",
        tools=tools,
        executores={"consultar_preco": consultar_preco, "consultar_frete": consultar_frete},
        max_turns=3,
    )
    explica("\nSe o modelo pediu as duas ferramentas no mesmo turno, repare que ambos os "
            "tool_result foram devolvidos JUNTOS antes do próximo turno do assistente.")


def demo_exit_conditions():
    header("3d) Definir condições de saída  🟢 (chamada real, loop deliberadamente sem fim natural)")
    explica("A ferramenta abaixo SEMPRE informa que 'há mais dados', tentando o modelo a "
            "chamá-la indefinidamente. Sem um max_turns no CÓDIGO, isso rodaria para sempre.")
    if not LIVE_MODE:
        aviso_sem_live()
        return

    tools = [{
        "name": "buscar_mais_dados",
        "description": "Busca a próxima página de dados de um relatório.",
        "input_schema": {"type": "object", "properties": {"pagina": {"type": "integer"}},
                          "required": ["pagina"]},
    }]

    def buscar_mais_dados(pagina):
        return {"pagina": pagina, "tem_mais_dados": True}  # nunca termina sozinho

    agent_loop(
        system_prompt="Você deve buscar todas as páginas de um relatório usando "
                      "buscar_mais_dados até não haver mais dados.",
        user_message="Busque todas as páginas do relatório de vendas, começando pela página 1.",
        tools=tools, executores={"buscar_mais_dados": buscar_mais_dados},
        max_turns=3,  # <-- condição de saída definida NO CÓDIGO, não no modelo
    )
    explica("\nO 'tem_mais_dados': True nunca muda -- só o max_turns definido no seu "
            "código impediu um loop infinito. Essa é a condição de saída que o artigo "
            "descreve como obrigatória.")


def menu_loop_steps():
    while True:
        header("TÓPICO 3: Os quatro passos do loop de um agente")
        print("1. Registrar ferramentas                          ⚪")
        print("2. Escopo do system prompt                        🟢")
        print("3. Loop de tool-use (múltiplas ferramentas/turno)  🟢")
        print("4. Definir condições de saída                     🟢")
        print("0. Voltar")
        escolha = input("\nEscolha: ").strip()
        if escolha == "1":
            demo_register_tools(); pausa()
        elif escolha == "2":
            demo_system_prompt_scope(); pausa()
        elif escolha == "3":
            demo_tool_use_loop(); pausa()
        elif escolha == "4":
            demo_exit_conditions(); pausa()
        elif escolha == "0":
            return
        else:
            print("Opção inválida.")


# ==========================================================================
# 4) HUMAN-IN-THE-LOOP (HITL)
# ==========================================================================

def demo_hitl_destrutiva():
    header("4a) HITL antes de chamada destrutiva (risco ALTO)  🟢 (chamada real)")
    explica("O modelo decide, sozinho, chamar uma ferramenta destrutiva. O CÓDIGO "
            "intercepta antes de executar e pede aprovação humana.")
    if not LIVE_MODE:
        aviso_sem_live()
        return

    tools = [{
        "name": "deletar_registro_cliente",
        "description": "Remove permanentemente o registro de um cliente (LGPD/GDPR).",
        "input_schema": {"type": "object", "properties": {"cliente_id": {"type": "integer"}},
                          "required": ["cliente_id"]},
    }]

    def deletar_registro_cliente(cliente_id):
        return {"cliente_id": cliente_id, "status": "deletado"}

    agent_loop(
        system_prompt="Você é um agente de atendimento que processa pedidos de remoção "
                      "de dados (LGPD). Use a ferramenta apropriada para atender ao pedido.",
        user_message="O cliente 5521 pediu a exclusão total dos seus dados. Execute a remoção.",
        tools=tools, executores={"deletar_registro_cliente": deletar_registro_cliente},
        max_turns=2, hitl_tools={"deletar_registro_cliente"},
    )


def demo_hitl_planejamento():
    header("4b) HITL após etapa de planejamento (risco MÉDIO)  🟢 (chamada real)")
    explica("Passo 1: o modelo elabora um PLANO em texto (sem executar nada). "
            "Passo 2: um humano aprova ou rejeita o plano inteiro. "
            "Passo 3: só então o agente executa as ferramentas.")
    if not LIVE_MODE:
        aviso_sem_live()
        return

    subheader("Passo 1: gerar o plano (sem ferramentas disponíveis ainda)")
    resposta_plano = uma_chamada(
        system_prompt="Elabore um plano de ação numerado e claro para o pedido do cliente. "
                      "NÃO execute nada ainda, apenas descreva o plano em texto.",
        user_message="O cliente tem 3 pedidos duplicados por engano, quer reembolso total "
                     "de R$890,00 e a empresa quer oferecer um cupom de 10% de cortesia.",
    )
    if resposta_plano is None:
        return

    subheader("Passo 2: aprovação humana do plano")
    resposta = input("O plano acima está correto? Aprovar execução? (s/n): ").strip().lower()
    if resposta != "s":
        print("[SEU CÓDIGO] Plano rejeitado -> agente deve replanejar ou escalar para humano.")
        return

    subheader("Passo 3: executar o plano aprovado")
    tools = [
        {"name": "cancelar_pedidos_duplicados", "description": "Cancela pedidos duplicados de um cliente.",
         "input_schema": {"type": "object", "properties": {"cliente_id": {"type": "integer"}},
                           "required": ["cliente_id"]}},
        {"name": "emitir_reembolso", "description": "Emite reembolso para o cliente.",
         "input_schema": {"type": "object", "properties": {
             "cliente_id": {"type": "integer"}, "valor": {"type": "number"}},
             "required": ["cliente_id", "valor"]}},
        {"name": "enviar_cupom", "description": "Envia um cupom de desconto ao cliente.",
         "input_schema": {"type": "object", "properties": {
             "cliente_id": {"type": "integer"}, "percentual": {"type": "number"}},
             "required": ["cliente_id", "percentual"]}},
    ]

    def cancelar_pedidos_duplicados(cliente_id):
        return {"cliente_id": cliente_id, "pedidos_cancelados": 3}

    def emitir_reembolso(cliente_id, valor):
        return {"cliente_id": cliente_id, "reembolso": valor, "status": "emitido"}

    def enviar_cupom(cliente_id, percentual):
        return {"cliente_id": cliente_id, "cupom_percentual": percentual, "status": "enviado"}

    agent_loop(
        system_prompt="Execute o plano já aprovado pelo humano usando as ferramentas disponíveis.",
        user_message="Cliente 4402: cancele os 3 pedidos duplicados, reembolse R$890,00 e "
                     "envie um cupom de cortesia de 10%.",
        tools=tools,
        executores={"cancelar_pedidos_duplicados": cancelar_pedidos_duplicados,
                    "emitir_reembolso": emitir_reembolso, "enviar_cupom": enviar_cupom},
        max_turns=4,
    )


def demo_hitl_output_inesperado():
    header("4c) HITL em saída inesperada (risco VARIÁVEL)  ⚪ (erro injetado deliberadamente)")
    explica("O resultado da ferramenta trouxe um flag de erro / valor fora do esperado -> "
            "não adianta só re-tentar. Esta seção injeta um erro deliberado no CÓDIGO "
            "(não depende do modelo), por isso permanece simulada/determinística.")

    resultado_ferramenta = {"status": "erro", "codigo": 500, "mensagem": "timeout no ERP"}
    print(f"[Resultado da ferramenta] {resultado_ferramenta}")

    if resultado_ferramenta.get("status") == "erro":
        print("[SISTEMA] Saída fora do esperado detectada. Retry automático não resolveria "
              "(erro de integração, não de transiência). Escalando para humano.")
        input("[Pressione Enter simulando que um humano foi notificado e está investigando]")
    else:
        print("[SISTEMA] Saída normal, loop continua sem intervenção.")


def menu_hitl():
    while True:
        header("TÓPICO 4: Human-in-the-Loop (HITL)")
        print("1. Antes de ação destrutiva (risco alto)          🟢")
        print("2. Após etapa de planejamento (risco médio)       🟢")
        print("3. Em saída inesperada (risco variável)           ⚪")
        print("0. Voltar")
        escolha = input("\nEscolha: ").strip()
        if escolha == "1":
            demo_hitl_destrutiva(); pausa()
        elif escolha == "2":
            demo_hitl_planejamento(); pausa()
        elif escolha == "3":
            demo_hitl_output_inesperado(); pausa()
        elif escolha == "0":
            return
        else:
            print("Opção inválida.")


# ==========================================================================
# 5) ORQUESTRAÇÃO DE FERRAMENTAS: over-tooling vs under-tooling
# ==========================================================================

def demo_over_tooling():
    header("5a) OVER-TOOLING — excesso de ferramentas sobrepostas  🟢 (duas chamadas reais)")
    explica("Registramos 6 ferramentas quase idênticas para 'buscar cliente'. Rodamos a "
            "MESMA pergunta duas vezes para observar se o modelo escolhe ferramentas "
            "diferentes entre as execuções (roteamento menos previsível).")
    if not LIVE_MODE:
        aviso_sem_live()
        return

    nomes = ["buscar_cliente", "buscar_cliente_por_email", "procurar_cliente",
             "consultar_cliente", "get_cliente", "cliente_lookup"]
    tools = [{"name": n, "description": "Busca os dados de um cliente pelo nome.",
              "input_schema": {"type": "object", "properties": {"nome": {"type": "string"}},
                                "required": ["nome"]}} for n in nomes]

    print(f"Ferramentas registradas (redundantes): {nomes}\n")
    pedido = "Encontre os dados do cliente João Silva."

    subheader("Execução 1")
    uma_chamada(system_prompt="Você consulta dados de clientes.", user_message=pedido, tools=tools)
    subheader("Execução 2 (mesma pergunta, chamada independente)")
    uma_chamada(system_prompt="Você consulta dados de clientes.", user_message=pedido, tools=tools)

    explica("\nCompare qual ferramenta foi escolhida em cada execução. Mesmo quando o "
            "modelo acerta, descrições sobrepostas aumentam a chance de escolhas "
            "inconsistentes entre execuções -- e dificultam observabilidade.")


def demo_under_tooling():
    header("5b) UNDER-TOOLING — ferramentas insuficientes  🟢 (chamada real)")
    explica("Registramos APENAS 'consultar_pedido', mas pedimos cancelamento + reembolso "
            "-- ações para as quais não existe ferramenta.")
    if not LIVE_MODE:
        aviso_sem_live()
        return

    tools = [{"name": "consultar_pedido", "description": "Consulta o status de um pedido.",
              "input_schema": {"type": "object", "properties": {"pedido_id": {"type": "integer"}},
                                "required": ["pedido_id"]}}]

    def consultar_pedido(pedido_id):
        return {"pedido_id": pedido_id, "status": "confirmado", "valor": 149.90}

    agent_loop(
        system_prompt="Você atende pedidos de clientes usando as ferramentas disponíveis.",
        user_message="Cancele o pedido 778 e reembolse o cliente.",
        tools=tools, executores={"consultar_pedido": consultar_pedido}, max_turns=2,
    )
    explica("\nRepare como o modelo reagiu à falta de ferramenta: normalmente ele consulta "
            "o que PODE consultar e explica, em texto, que não tem como cancelar/reembolsar "
            "-- exatamente a 'resposta incompleta' descrita no artigo.")


def demo_right_sized_tooling():
    header("5c) Conjunto de ferramentas bem dimensionado  🟢 (chamada real)")
    explica("Agora registramos exatamente o necessário: consultar, cancelar e reembolsar.")
    if not LIVE_MODE:
        aviso_sem_live()
        return

    tools = [
        {"name": "consultar_pedido", "description": "Consulta o status de um pedido.",
         "input_schema": {"type": "object", "properties": {"pedido_id": {"type": "integer"}},
                           "required": ["pedido_id"]}},
        {"name": "cancelar_pedido", "description": "Cancela um pedido existente.",
         "input_schema": {"type": "object", "properties": {"pedido_id": {"type": "integer"}},
                           "required": ["pedido_id"]}},
        {"name": "emitir_reembolso", "description": "Emite o reembolso de um pedido cancelado.",
         "input_schema": {"type": "object", "properties": {
             "pedido_id": {"type": "integer"}, "valor": {"type": "number"}},
             "required": ["pedido_id", "valor"]}},
    ]

    def consultar_pedido(pedido_id):
        return {"pedido_id": pedido_id, "status": "confirmado", "valor": 149.90}

    def cancelar_pedido(pedido_id):
        return {"pedido_id": pedido_id, "status": "cancelado"}

    def emitir_reembolso(pedido_id, valor):
        return {"pedido_id": pedido_id, "reembolso": valor, "status": "emitido"}

    agent_loop(
        system_prompt="Você atende pedidos de clientes usando as ferramentas disponíveis.",
        user_message="Cancele o pedido 778 e reembolse o cliente.",
        tools=tools,
        executores={"consultar_pedido": consultar_pedido, "cancelar_pedido": cancelar_pedido,
                    "emitir_reembolso": emitir_reembolso},
        max_turns=4,
    )
    explica("\n-> Com o conjunto certo de ferramentas, o roteamento fica previsível e "
            "sem ambiguidade, sem lacuna de capacidade.")


def menu_tool_orchestration():
    while True:
        header("TÓPICO 5: Orquestração de ferramentas")
        print("1. Over-tooling (ferramentas demais)              🟢")
        print("2. Under-tooling (ferramentas de menos)           🟢")
        print("3. Conjunto bem dimensionado                      🟢")
        print("0. Voltar")
        escolha = input("\nEscolha: ").strip()
        if escolha == "1":
            demo_over_tooling(); pausa()
        elif escolha == "2":
            demo_under_tooling(); pausa()
        elif escolha == "3":
            demo_right_sized_tooling(); pausa()
        elif escolha == "0":
            return
        else:
            print("Opção inválida.")


# ==========================================================================
# 6) RESTRIÇÕES REGULATÓRIAS -> ROTA DE ENTREGA
# ==========================================================================

ROTAS_REGULATORIAS = {
    "1": {
        "nome": "Privilégio advogado-cliente",
        "descarta": "Chamadas via Claude.ai consumer, ou qualquer endpoint não auditado pelo escritório.",
        "usa": "API/SDK direto de dentro da aplicação do escritório, autenticado via SSO, "
               "roteado por gateway aprovado com logging completo na camada de aplicação.",
    },
    "2": {
        "nome": "HIPAA (dados de saúde / PHI)",
        "descarta": "Qualquer endpoint sem BAA para a configuração específica em uso "
                    "(inclui Console, Workbench, betas e planos consumer).",
        "usa": "API/SDK direto em configuração coberta por BAA (organização HIPAA dedicada), "
               "ou rota via AWS Bedrock / GCP Vertex já cobertos pelo BAA existente do parceiro.",
    },
    "3": {
        "nome": "GDPR / residência de dados na UE",
        "descarta": "Endpoint global sem região fixada; API direta da Anthropic "
                    "(não oferece residência de dados na UE atualmente).",
        "usa": "Rota via AWS Bedrock ou GCP Vertex, com a região fixada na configuração "
               "do cliente para a jurisdição aprovada.",
    },
    "4": {
        "nome": "FedRAMP / governo",
        "descarta": "Qualquer chamada a endpoint fora do ambiente de nuvem autorizado no "
                    "nível de impacto exigido; misturar dev/test no endpoint comercial.",
        "usa": "Claude for Government (via PFCS-SS, FedRAMP High), Bedrock GovCloud "
               "(FedRAMP High / DoD IL4-5), ou Vertex AI Assured Workloads.",
    },
    "5": {
        "nome": "Política interna de residência de dados",
        "descarta": "Cliente SDK configurado contra provedor de nuvem fora da lista aprovada "
                    "pela organização, mesmo que tecnicamente funcione.",
        "usa": "Rota de entrega no provedor de nuvem já aprovado pelo CIO/procurement da empresa.",
    },
}


def decide_endpoint(chave_constraint: str) -> dict:
    return ROTAS_REGULATORIAS.get(chave_constraint)


def demo_compliance_routing():
    header("6) Restrições regulatórias definem o endpoint ANTES do design  ⚪ (lógica pura)")
    explica(
        "A restrição de dados decide qual endpoint seu código chama, quais credenciais "
        "carrega e onde os logs ficam -- antes de qualquer decisão sobre prompts ou "
        "ferramentas. Isso é decisão de arquitetura/compliance, não de modelo."
    )

    print("\nTipos de restrição disponíveis:")
    for k, v in ROTAS_REGULATORIAS.items():
        print(f"  {k}. {v['nome']}")

    escolha = input("\nEscolha uma restrição para ver a rota decidida: ").strip()
    rota = decide_endpoint(escolha)
    if not rota:
        print("Opção inválida.")
        return

    subheader(f"Restrição selecionada: {rota['nome']}")
    print("O que isso DESCARTA no código:")
    explica(f"   {rota['descarta']}")
    print("\nO que normalmente SOBREVIVE à revisão de código:")
    explica(f"   {rota['usa']}")


# ==========================================================================
# MENU PRINCIPAL
# ==========================================================================

def status_modo():
    if LIVE_MODE:
        return (f"MODO: 🟢 LIVE — chamadas reais habilitadas (modelo: {MODEL_NAME}, "
                f".env carregado via {_MODO_ENV})")
    linhas = ["MODO: ⚪ SEM CHAVE — seções 🟢 vão avisar e não chamarão a API."]
    if _MOTIVO_SEM_LIVE:
        linhas.append(f"       Motivo: {_MOTIVO_SEM_LIVE}")
    return "\n".join(linhas)


def main_menu():
    while True:
        header("AGENT CONCEPTS DEMO — Certificação Claude Developer")
        print(status_modo())
        print("""
1. Workflow vs Agente
2. Caminhos de Wiring (Raw Loop / Agent SDK / Managed Agents)
3. Os quatro passos do loop de um agente
4. Human-in-the-Loop (HITL)
5. Orquestração de ferramentas (over/under-tooling)
6. Restrições regulatórias -> rota de entrega
0. Sair

Legenda: 🟢 = chamada real à API   ⚪ = demonstração simulada/lógica
""")
        escolha = input("Escolha um tópico: ").strip()
        if escolha == "1":
            menu_workflow_vs_agent()
        elif escolha == "2":
            menu_wiring_paths()
        elif escolha == "3":
            menu_loop_steps()
        elif escolha == "4":
            menu_hitl()
        elif escolha == "5":
            menu_tool_orchestration()
        elif escolha == "6":
            demo_compliance_routing(); pausa()
        elif escolha == "0":
            print("Até mais!")
            sys.exit(0)
        else:
            print("Opção inválida.")


if __name__ == "__main__":
    main_menu()