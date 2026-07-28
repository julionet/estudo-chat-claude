"""
Chat com contexto: mantém o histórico da conversa a cada turno.
Digite 'exit' para encerrar.
"""

import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(
    api_key=API_KEY
)

MODEL = "claude-haiku-4-5-20251001"
LIMITE_TOKENS = 4096
LIMIAR_RESUMO = 0.75  # dispara o resumo ao atingir esta fração do limite de tokens
MENSAGENS_RECENTES = 4  # últimos turnos (user+assistant) mantidos intactos, sem resumir

CEPS_FICTICIOS = {
    "01310-100": "Av. Paulista, 1000 - Bela Vista, São Paulo - SP",
    "20040-020": "Rua da Assembleia, 10 - Centro, Rio de Janeiro - RJ",
    "30130-010": "Av. Afonso Pena, 1500 - Centro, Belo Horizonte - MG",
    "40010-000": "Rua Chile, 20 - Centro, Salvador - BA",
    "50030-230": "Av. Conde da Boa Vista, 500 - Boa Vista, Recife - PE",
    "60060-170": "Av. Santos Dumont, 300 - Aldeota, Fortaleza - CE",
    "70040-010": "Esplanada dos Ministérios, 1 - Zona Cívico-Administrativa, Brasília - DF",
    "80010-000": "Rua XV de Novembro, 100 - Centro, Curitiba - PR",
    "90010-000": "Av. Borges de Medeiros, 400 - Centro Histórico, Porto Alegre - RS",
    "13010-050": "Rua Barão de Jaguara, 200 - Centro, Campinas - SP",
}

PRODUTOS_FICTICIOS = [
    {"nome": "Notebook", "categoria": "Eletrônicos", "valor": 3500.00},
    {"nome": "Smartphone", "categoria": "Eletrônicos", "valor": 2200.00},
    {"nome": "Fone de Ouvido", "categoria": "Eletrônicos", "valor": 150.00},
    {"nome": "Camiseta", "categoria": "Vestuário", "valor": 60.00},
    {"nome": "Calça Jeans", "categoria": "Vestuário", "valor": 120.00},
    {"nome": "Tênis", "categoria": "Vestuário", "valor": 250.00},
    {"nome": "Arroz 5kg", "categoria": "Alimentos", "valor": 25.00},
    {"nome": "Feijão 1kg", "categoria": "Alimentos", "valor": 8.00},
    {"nome": "Café 500g", "categoria": "Alimentos", "valor": 15.00},
    {"nome": "Sofá 3 Lugares", "categoria": "Móveis", "valor": 1800.00},
]

TOOLS = [
    {
        "name": "buscar_endereco_cep",
        "description": "Busca o endereço vinculado a um CEP em uma base cadastrada. Use quando o usuário informar um CEP e pedir o endereço correspondente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cep": {"type": "string", "description": "CEP a ser consultado, ex: 01310-100"}
            },
            "required": ["cep"]
        }
    },
    {
        "name": "somar_produtos_categoria",
        "description": "Retorna a soma total dos valores dos produtos de uma categoria em uma base cadastrada. Use quando o usuário pedir o total gasto ou soma de produtos de uma categoria.",
        "input_schema": {
            "type": "object",
            "properties": {
                "categoria": {"type": "string", "description": "Nome da categoria dos produtos, ex: Eletrônicos"}
            },
            "required": ["categoria"]
        }
    }
]

def buscar_endereco_cep(cep):
    """Busca o endereço vinculado a um CEP na base fictícia."""
    cep_normalizado = cep.strip()
    endereco = CEPS_FICTICIOS.get(cep_normalizado)
    if endereco:
        return {"cep": cep_normalizado, "endereco": endereco}
    return {"erro": f"CEP {cep_normalizado} não encontrado na base."}

def somar_produtos_categoria(categoria):
    """Soma o valor total dos produtos de uma categoria na base fictícia."""
    categoria_normalizada = categoria.strip().lower()
    produtos = [p for p in PRODUTOS_FICTICIOS if p["categoria"].lower() == categoria_normalizada]
    if not produtos:
        return {"erro": f"Nenhum produto encontrado para a categoria '{categoria}'."}
    total = sum(p["valor"] for p in produtos)
    return {
        "categoria": categoria,
        "quantidade_produtos": len(produtos),
        "total": round(total, 2),
        "produtos": [p["nome"] for p in produtos]
    }

def executar_tool(nome, entrada):
    """Despacha a execução da tool solicitada pelo modelo."""
    if nome == "buscar_endereco_cep":
        return buscar_endereco_cep(entrada["cep"])
    if nome == "somar_produtos_categoria":
        return somar_produtos_categoria(entrada["categoria"])
    return {"erro": f"Tool '{nome}' não reconhecida."}

def resumir_historico(historico):
    """Resume os turnos mais antigos do histórico, mantendo os mais recentes intactos."""
    if len(historico) <= MENSAGENS_RECENTES:
        return historico

    antigo = historico[:-MENSAGENS_RECENTES]
    recentes = historico[-MENSAGENS_RECENTES:]

    antigo_para_resumir = antigo + [
        {"role": "user", "content": "Resuma todas as perguntas e respostas anteriores."}
    ]

    resumo = None
    for tentativa in range(1, 4):
        resposta = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=(
                "Resuma a conversa abaixo de forma concisa, preservando fatos, decisões "
                "e contexto necessário para dar continuidade à conversa. Não invente informação."
            ),
            messages=antigo_para_resumir
        )
        if resposta.content and resposta.content[0].text:
            resumo = resposta.content[0].text
            break
        print(f"⚠️ Resumo vazio (tentativa {tentativa}/3). Tentando novamente...")

    if resumo is None:
        print("⚠️ Não foi possível gerar o resumo após 3 tentativas. Mantendo histórico original.")
        return historico

    novo_historico = [
        {"role": "user", "content": f"[Resumo da conversa anterior]: {resumo}"},
        {"role": "assistant", "content": "Entendido, vou considerar esse contexto."}
    ]
    novo_historico.extend(recentes)
    return novo_historico

def main():
    print("Conversa iniciada. Digite 'exit' para encerrar.\n")

    system_prompt = input("Prompt de sistema (opcional, Enter para pular): ").strip()
    print()

    historico = []  # acumula todos os turnos: user + assistant

    while True:
        pergunta = input("Voce: ").strip()

        if pergunta.lower() == "exit":
            print("Conversa encerrada.")
            break

        if not pergunta:
            print("Nenhuma pergunta informada. Tente novamente.\n")
            continue

        # Verifica o histórico acumulado (turnos completos) antes de adicionar a nova pergunta
        if historico:
            contagem_atual = client.messages.count_tokens(
                model=MODEL,
                system=system_prompt,
                messages=historico
            )
            if contagem_atual.input_tokens > LIMITE_TOKENS * LIMIAR_RESUMO:
                print("\n♻️ Resumindo histórico da conversa para liberar espaço...\n")
                historico = resumir_historico(historico)

        # Adiciona a mensagem do usuário ao histórico antes de enviar
        historico.append({"role": "user", "content": pergunta})

        contagem = client.messages.count_tokens(
            model=MODEL,
            system=system_prompt,
            messages=historico
        )

        if contagem.input_tokens > LIMITE_TOKENS:
            print(f"\n⚠️ Aviso: a conversa está usando {contagem.input_tokens} tokens, "
                  f"acima do limite de {LIMITE_TOKENS}.\n")

        # Loop de chamadas à API: repete enquanto o modelo solicitar o uso de tools
        while True:
            print("\nClaude: ", end="", flush=True)

            conteudo_resposta = []
            resposta_texto = ""

            with client.messages.stream(
                model=MODEL,
                max_tokens=LIMITE_TOKENS,
                system=system_prompt,
                messages=historico,
                tools=TOOLS
            ) as stream:
                for evento in stream:
                    # Coleta blocos de conteúdo (text, tool_use, etc)
                    if evento.type == "content_block_start":
                        conteudo_resposta.append(evento.content_block)

                    # Processa eventos de delta (texto ou JSON)
                    elif evento.type == "content_block_delta":
                        if evento.delta.type == "text_delta":
                            texto = evento.delta.text
                            print(texto, end="", flush=True)
                            resposta_texto += texto

                        elif evento.delta.type == "input_json_delta":
                            # Atualiza JSON de tool_use durante streaming
                            if conteudo_resposta:
                                ultimo_bloco = conteudo_resposta[-1]
                                if hasattr(ultimo_bloco, "input"):
                                    if not hasattr(ultimo_bloco, "_input_str"):
                                        ultimo_bloco._input_str = ""
                                    ultimo_bloco._input_str += evento.delta.input_json

                # Obtém a resposta final após o stream
                response = stream.get_final_message()

            print("\n")  # Nova linha após streaming

            if response.stop_reason == "max_tokens":
                print("⚠️ Erro: a resposta foi truncada por atingir o limite de tokens.")
                print("Aumente o valor de max_tokens e tente novamente.\n")
                historico.pop()
                break

            if response.stop_reason == "tool_use":
                # Guarda a solicitação de tool_use do modelo no histórico
                historico.append({"role": "assistant", "content": response.content})

                resultados_tools = []
                for bloco in response.content:
                    if bloco.type == "tool_use":
                        print(f"🔧 Executando tool '{bloco.name}' com entrada {bloco.input}...\n")
                        resultado = executar_tool(bloco.name, bloco.input)
                        resultados_tools.append({
                            "type": "tool_result",
                            "tool_use_id": bloco.id,
                            "content": json.dumps(resultado, ensure_ascii=False)
                        })

                # Envia o resultado das tools de volta e chama a API novamente
                historico.append({"role": "user", "content": resultados_tools})
                continue

            if response.stop_reason == "end_turn":
                # Adiciona a resposta do Claude ao histórico para o próximo turno
                historico.append({"role": "assistant", "content": resposta_texto if resposta_texto else response.content[0].text})
                break

if __name__ == "__main__":
    main()
