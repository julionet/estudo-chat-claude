import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

MAX_TOKENS = 4096
LIMIT_TOKENS = 1024
LIMIAR_TOKENS = 0.7
RECENT_MESSAGES = 3

TOOLS = [
    {
        "name": "obter_informacoes_usuario",
        "description": "Retorna informações de um usuário fictício de acordo com um ID. Use quando for pedido para buscar informações de um usuário não quando for pedido para buscar total de compras.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID do usuário fictício. Ex: 100"}
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "obter_valor_total_compras",
        "description": "Retorna o valor total de compras de um usuário fictício. Use quando for pedido para buscar o valor total de compras de um usuário não quando for pedido para buscar dados ou informações.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID do usuário fictício. Ex: 100"}
            },
            "required": ["user_id"]
        }
    }
]

client = anthropic.Anthropic(api_key=API_KEY)

def resume_history(history):
    if len(history) <= RECENT_MESSAGES:
            return history
    
    antigo = history[:-RECENT_MESSAGES]
    recentes = history[-RECENT_MESSAGES:]

    old_to_resume = antigo + [
            {"role": "user", "content": "Resuma todas as perguntas e respostas anteriores."}
        ]

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=create_system_cache("Resuma a conversa abaixo de forma concisa, preservando fatos, decisões "
                            "e contexto necessário para dar continuidade à conversa. Não invente informação."),
            messages=old_to_resume
        )
    except Exception as e:
        print(f"Ocorreu um erro ao resumir o histórico: {e}")
        return None

    resumo = next((b.text for b in response.content if b.type == "text"), "")

    if resumo is None:
        print("Não foi possível obter o resumo do histórico.")
        return history

    new_history = [
        {"role": "user", "content": f"[Resumo da conversa]: {resumo}"},
        {"role": "assistant", "content": "Entendido, vou considerar esse contexto."}
    ]
    new_history.extend(recentes)
    return new_history

def count_tokens(system_prompt, history):
    try:
        contagem = client.messages.count_tokens(
            model=MODEL,
            system=system_prompt,
            messages=history
        )
        return contagem
    except Exception as e:
        print(f"Ocorreu um erro ao contar tokens: {e}")
        return None
    
def create_system_cache(system_prompt):
    return [{
        "type": "text", 
        "text": system_prompt, 
        "cache_control": {"type": "ephemeral"}
    }]

def use_no_streaming_response(system_prompt, history):
    print("\nClaude: ", end="", flush=True)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=create_system_cache(system_prompt),
            messages=history,
            tools=TOOLS
        )
    except Exception as e:
        print(f"\nOcorreu um erro ao gerar a resposta: {e}")
        return None, None

    print(f"cache_creation_input_tokens: {response.usage.cache_creation_input_tokens}")
    print(f"cache_read_input_tokens: {response.usage.cache_read_input_tokens}")

    resposta = next((b.text for b in response.content if b.type == "text"), "")
    print(resposta, end="", flush=True)

    return response, resposta

def use_streaming_response(system_prompt, history):
    print("\nClaude: ", end="", flush=True)

    resposta = ""

    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=create_system_cache(system_prompt),
        messages=history
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                resposta += event.delta.text
                print(event.delta.text, end="", flush=True)

        response = stream.get_final_message()

    return response, resposta

def example_tool1(input_data):
    return { "nome": "Jose", "idade": 30, "cidade": "Sao Paulo" }

def example_tool2(input_data):
    return { "valor_compras": 200.0 }

def execute_tool(tool_name, tool_input):
    if tool_name == "example_tool1":
        return example_tool1(tool_input)
    elif tool_name == "example_tool2":
        return example_tool2(tool_input)
    return {"erro": f"Tool '{tool_name}' não reconhecida."}

def main():
    system_prompt = input("Digite o prompt do sistema: ")

    history = []

    while True:
        print()
        user_prompt = input("Voce: ").strip()

        if user_prompt.lower() in ["sair", "exit", "quit"]:
            break

        if not user_prompt:
            print("Nenhuma pergunta informada. Tente novamente.\n")
            continue

        history.append({"role": "user", "content": user_prompt})

        contagem = count_tokens(system_prompt, history)
        if contagem is None:
            print("Não foi possível contar os tokens. Tente novamente.\n")
            history.pop()
            continue

        if contagem.input_tokens > LIMIT_TOKENS * LIMIAR_TOKENS:
            print("\n♻️ Resumindo histórico da conversa para liberar espaço...\n")
            history = resume_history(history)
            continue

        while True:
            response, content = use_no_streaming_response(system_prompt, history)

            if response is None:
                break

            if response.stop_reason == "tool_use":
                history.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        retorno = execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(retorno, ensure_ascii=False)
                        })

                history.append({"role": "user", "content": tool_results})
                continue

            if response.stop_reason == "max_tokens":
                print("\nA resposta foi interrompida antes de ser concluída por limite de tokens. Tente novamente.\n")
                history.pop() 
                continue

            elif response.stop_reason == "end_turn":
                history.append({"role": "assistant", "content": content})
                break

if __name__ == "__main__":
    main()
