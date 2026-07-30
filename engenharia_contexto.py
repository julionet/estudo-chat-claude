#!/usr/bin/env python3
"""
================================================================================
DEMO: Engenharia de Contexto com a API da Anthropic
================================================================================

Aplicação de exemplo para a certificação Claude Developer, cobrindo cada
conceito da documentação de "Model selection and keeping multi-turn sessions
in budget":

  1. Seleção de modelo (Sonnet como padrão, Opus/Haiku/Fable por avaliação)
  2. Janela de contexto e token counting (count_tokens)
  3. Prompt caching (cache_control ephemeral)
  4. Pruning (voltar a um ponto anterior da conversa)
  5. Compactação (resumir o histórico preservando estado crítico)
  6. Clearing (nova sessão com contexto vazio)
  7. Subagent handoffs (contexto isolado + resumo)
  8. RAG: chunking, embedding match (simulado) e assembly

Requisitos:
    pip install anthropic
    export ANTHROPIC_API_KEY="sua-chave-aqui"

Execução:
    python3 context_engineering_demo.py
================================================================================
"""

import os
import sys
import time
from dataclasses import dataclass, field

try:
    import anthropic
except ImportError:
    print("Pacote 'anthropic' não encontrado. Instale com: pip install anthropic")
    sys.exit(1)


# ------------------------------------------------------------------------
# Configuração geral
# ------------------------------------------------------------------------

# Modelos atuais da família Claude (confirme sempre em platform.claude.com/docs
# antes de usar em produção — nomes de modelo mudam com o tempo).
MODELS = {
    "haiku": "claude-haiku-4-5-20251001",   # rápido/barato
    "sonnet": "claude-sonnet-5",            # padrão balanceado
    "opus": "claude-opus-4-8",              # tarefas exigentes
    "fable": "claude-fable-5",              # máxima capacidade
}

MAX_TOKENS_DEMO = 300  # baixo de propósito, para manter as demos rápidas/baratas


def get_client() -> anthropic.Anthropic:
    """Cria o client usando ANTHROPIC_API_KEY do ambiente."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n⚠️  ANTHROPIC_API_KEY não está definida no ambiente.")
        print("   Defina com: export ANTHROPIC_API_KEY='sua-chave-aqui'\n")
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def pause():
    input("\nPressione ENTER para voltar ao menu...")


def hr(title: str = ""):
    print("\n" + "=" * 78)
    if title:
        print(title)
        print("=" * 78)


# ------------------------------------------------------------------------
# 1. SELEÇÃO DE MODELO
# ------------------------------------------------------------------------
def demo_model_selection(client: anthropic.Anthropic):
    """
    Conceito: comece com Sonnet (padrão balanceado); só suba para Opus/Fable
    se um eval mostrar que Sonnet não atinge a qualidade necessária; só desça
    para Haiku se a perda de qualidade for aceitável para a tarefa.

    Esta demo faz a MESMA pergunta a Haiku e a Sonnet e mostra latência,
    tokens de saída e a resposta — para você comparar o trade-off na prática.
    """
    hr("1) SELEÇÃO DE MODELO — comparando Haiku vs Sonnet na mesma tarefa")

    prompt = (
        "Explique em 2 frases o que é 'context engineering' em aplicações "
        "com LLMs, para um desenvolvedor iniciante."
    )
    print(f"Prompt de teste: {prompt!r}\n")

    for nome in ("haiku", "sonnet"):
        modelo = MODELS[nome]
        inicio = time.time()
        resposta = client.messages.create(
            model=modelo,
            max_tokens=MAX_TOKENS_DEMO,
            messages=[{"role": "user", "content": prompt}],
        )
        duracao = time.time() - inicio
        texto = "".join(b.text for b in resposta.content if b.type == "text")

        print(f"--- Modelo: {nome} ({modelo}) ---")
        print(f"Latência: {duracao:.2f}s")
        print(f"Tokens entrada/saída: {resposta.usage.input_tokens}/"
              f"{resposta.usage.output_tokens}")
        print(f"Resposta: {texto.strip()}\n")

    print(
        "Ponto-chave: a decisão de qual modelo usar deve ser guiada por evals\n"
        "(qualidade medida), não por intuição — suba de nível só quando o\n"
        "modelo padrão (Sonnet) comprovadamente não atende ao seu bar de\n"
        "qualidade, e desça para Haiku só quando a perda for aceitável."
    )
    pause()


# ------------------------------------------------------------------------
# 2. JANELA DE CONTEXTO E TOKEN COUNTING
# ------------------------------------------------------------------------
def demo_token_counting(client: anthropic.Anthropic):
    """
    Conceito: a janela de contexto não é um recurso gratuito. O endpoint
    count_tokens mede a pressão sobre o contexto ANTES de enviar a
    requisição, sem rodar inferência (não gera custo de geração).
    """
    hr("2) JANELA DE CONTEXTO — medindo tokens antes de enviar (count_tokens)")

    # Simula um "tool result" grande, como aconteceria em produção
    tool_result_grande = (
        "RESULTADO_DA_FERRAMENTA: " + ("dados de exemplo repetidos. " * 200)
    )
    historico = [
        {"role": "user", "content": "Resuma o relatório de vendas do Q3."},
        {"role": "assistant", "content": "Claro, vou buscar os dados."},
        {"role": "user", "content": tool_result_grande},
    ]

    contagem = client.messages.count_tokens(
        model=MODELS["sonnet"],
        messages=historico,
    )
    print(f"Tokens estimados nesta conversa até agora: {contagem.input_tokens}")
    print(
        "\nEm desenvolvimento, esse número costuma ser pequeno (fixtures de\n"
        "teste). Em produção, tool outputs reais são 3-5x maiores — por isso\n"
        "a janela pode encher no turno 8 em vez do turno 50. Medir com\n"
        "count_tokens antes de disparar a chamada real permite bloquear ou\n"
        "acionar pruning/compactação antes do erro "
        "'model_context_window_exceeded'."
    )
    pause()


# ------------------------------------------------------------------------
# 3. PROMPT CACHING
# ------------------------------------------------------------------------
def demo_prompt_caching(client: anthropic.Anthropic):
    """
    Conceito: prompt caching guarda o processamento de um prefixo estável
    (system prompt longo, documento de referência) para reaproveitar em
    chamadas seguintes a custo reduzido. Marca-se com cache_control
    (type=ephemeral) no último bloco que se quer cachear.
    """
    hr("3) PROMPT CACHING — reaproveitando um prefixo estável")

    # Um "documento de referência" propositalmente longo para tornar o cache
    # visível no relatório de uso (cache mínimo costuma exigir texto longo).
    documento_referencia = (
        "MANUAL INTERNO DE ATENDIMENTO AO CLIENTE.\n"
        + ("Política de reembolso: reembolsos são processados em até 5 dias "
           "úteis após aprovação. " * 400)
    )

    system_com_cache = [
        {
            "type": "text",
            "text": documento_referencia,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    print("Chamada 1 (grava o prefixo no cache)...")
    r1 = client.messages.create(
        model=MODELS["sonnet"],
        max_tokens=MAX_TOKENS_DEMO,
        system=system_com_cache,
        messages=[{"role": "user", "content": "Qual o prazo de reembolso?"}],
    )
    print(f"  cache_creation_input_tokens: "
          f"{getattr(r1.usage, 'cache_creation_input_tokens', 0)}")
    print(f"  cache_read_input_tokens:     "
          f"{getattr(r1.usage, 'cache_read_input_tokens', 0)}")

    print("\nChamada 2 (reaproveita o mesmo prefixo do cache)...")
    r2 = client.messages.create(
        model=MODELS["sonnet"],
        max_tokens=MAX_TOKENS_DEMO,
        system=system_com_cache,
        messages=[{"role": "user", "content": "E se o pagamento foi no cartão?"}],
    )
    print(f"  cache_creation_input_tokens: "
          f"{getattr(r2.usage, 'cache_creation_input_tokens', 0)}")
    print(f"  cache_read_input_tokens:     "
          f"{getattr(r2.usage, 'cache_read_input_tokens', 0)}")

    print(
        "\nPonto-chave: na 2ª chamada, cache_read_input_tokens deve aparecer\n"
        "> 0 e cache_creation_input_tokens deve ser 0 — o prefixo foi lido\n"
        "do cache em vez de reprocessado, reduzindo custo/latência. Bom para\n"
        "system prompts longos, definições de ferramentas ou documentos\n"
        "consultados repetidamente."
    )
    pause()


# ------------------------------------------------------------------------
# 4. PRUNING
# ------------------------------------------------------------------------
def demo_pruning(client: anthropic.Anthropic):
    """
    Conceito: pruning volta a uma mensagem anterior e descarta tudo que veio
    depois — útil quando o agente foi por um caminho improdutivo. O que foi
    aprendido depois do ponto de corte é perdido.
    """
    hr("4) PRUNING — descartando um caminho improdutivo da conversa")

    historico = [
        {"role": "user", "content": "Me ajude a escrever uma função em Python "
                                     "para calcular a média de uma lista."},
    ]
    r1 = client.messages.create(
        model=MODELS["sonnet"], max_tokens=MAX_TOKENS_DEMO, messages=historico
    )
    resposta1 = "".join(b.text for b in r1.content if b.type == "text")
    historico.append({"role": "assistant", "content": resposta1})
    print("--- Turno 1 (mantido) ---")
    print(resposta1.strip()[:300], "\n")

    # Simula um caminho de debug improdutivo que "poluiu" o contexto
    historico.append({
        "role": "user",
        "content": "Na verdade, ignore isso, tentei usar numpy mas deu um "
                    "erro de import gigante, deixa eu colar o traceback "
                    "inteiro..."
    })
    historico.append({
        "role": "assistant",
        "content": "[longa investigação de debug irrelevante para a tarefa "
                    "original — 40 linhas de troca sobre ambiente virtual]"
    })
    print("--- Turno 2 (caminho improdutivo, ANTES do pruning) ---")
    print("(debug de ambiente que não ajuda a tarefa original)\n")

    # PRUNING: volta ao ponto logo após o turno 1, descartando o resto
    ponto_de_corte = 2  # mantém só as 2 primeiras mensagens (user + assistant)
    historico_podado = historico[:ponto_de_corte]
    print(f"--- Aplicando pruning: mantendo só as {ponto_de_corte} primeiras "
          f"mensagens ---")

    historico_podado.append({
        "role": "user",
        "content": "Agora adicione tratamento para lista vazia na função."
    })
    r2 = client.messages.create(
        model=MODELS["sonnet"], max_tokens=MAX_TOKENS_DEMO,
        messages=historico_podado
    )
    resposta2 = "".join(b.text for b in r2.content if b.type == "text")
    print("--- Turno 3 (continua a partir do ponto podado, sem o ruído) ---")
    print(resposta2.strip()[:300])

    print(
        "\nPonto-chave: o histórico enviado na 3ª chamada NÃO contém o "
        "desvio\nde debug — voltamos a um ponto anterior e seguimos dali, "
        "economizando\ntokens e evitando que o ruído influencie a próxima "
        "resposta."
    )
    pause()


# ------------------------------------------------------------------------
# 5. COMPACTAÇÃO
# ------------------------------------------------------------------------
def demo_compaction(client: anthropic.Anthropic):
    """
    Conceito: compactação resume o histórico preservando informação-chave.
    O que é preservado depende de como você escreve o prompt do
    summarizer — um prompt vago ("resuma a conversa") perde estado crítico;
    um prompt específico preserva o que importa para a tarefa continuar.
    """
    hr("5) COMPACTAÇÃO — comparando um summarizer vago vs. um específico")

    conversa_longa = """
Usuário: Preciso migrar o serviço de pagamentos de Python 2 para Python 3.
Assistente: Ok, vou começar pelo arquivo payments/processor.py.
Usuário: Lembre de manter compatibilidade com o formato de log antigo.
Assistente: Entendido. Troquei print statements por print() em processor.py.
Usuário: Achei um bug: a função calculate_fee() está dividindo por zero
quando o valor é 0.
Assistente: Corrigido em processor.py linha 42, adicionei checagem
`if amount == 0: return 0` antes da divisão.
Assistente: Também migrei utils/currency.py e tests/test_processor.py.
Usuário: O teste test_processor.py::test_fee_calculation ainda está
falhando com AssertionError: esperado 10.5, obtido 10.4999999.
Assistente: Era arredondamento de float. Resolvido usando
round(fee, 2) na linha 58 de processor.py.
"""

    print("Conversa original (resumida aqui só para exibição)...\n")

    # --- Summarizer VAGO ---
    resumo_vago = client.messages.create(
        model=MODELS["sonnet"],
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": f"Resuma a conversa a seguir.\n\n{conversa_longa}",
        }],
    )
    texto_vago = "".join(b.text for b in resumo_vago.content if b.type == "text")
    print("--- Resumo com prompt VAGO ('resuma a conversa') ---")
    print(texto_vago.strip(), "\n")

    # --- Summarizer ESPECÍFICO ---
    resumo_especifico = client.messages.create(
        model=MODELS["sonnet"],
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": (
                "Resuma a conversa a seguir preservando: (1) todos os "
                "caminhos de arquivo modificados, (2) todas as decisões "
                "tomadas, (3) todos os erros encontrados e suas resoluções "
                "exatas.\n\n" + conversa_longa
            ),
        }],
    )
    texto_especifico = "".join(
        b.text for b in resumo_especifico.content if b.type == "text"
    )
    print("--- Resumo com prompt ESPECÍFICO (preserva arquivos/decisões/erros) ---")
    print(texto_especifico.strip())

    print(
        "\nPonto-chave: repare se o resumo específico cita payments/"
        "processor.py,\nutils/currency.py, a checagem de divisão por zero e "
        "o round(fee, 2) —\ndetalhes que o resumo vago tende a perder. Perda "
        "de estado crítico por\nsummarizer mal especificado é uma causa "
        "comum de falha em agentes\nmulti-sessão."
    )
    pause()


# ------------------------------------------------------------------------
# 6. CLEARING
# ------------------------------------------------------------------------
def demo_clearing(client: anthropic.Anthropic):
    """
    Conceito: clearing começa uma nova conversa com contexto vazio. Nada da
    sessão anterior carrega adiante — o que precisar ser lembrado tem que
    estar em algo persistente (ex.: um arquivo de estado, como CLAUDE.md).
    """
    hr("6) CLEARING — nova sessão com contexto vazio")

    # "Sessão anterior" — só existe na memória local do processo
    sessao_anterior = [
        {"role": "user", "content": "Meu projeto se chama 'ProjetoFênix' e "
                                     "usa FastAPI + PostgreSQL."},
        {"role": "assistant", "content": "Entendido, vou lembrar disso "
                                          "durante esta conversa."},
    ]
    print("Sessão anterior (em memória, não persistida em nenhum arquivo):")
    for m in sessao_anterior:
        print(f"  [{m['role']}] {m['content']}")

    print("\n--- Executando CLEAR: nova sessão, contexto vazio ---\n")

    # Nova sessão real: só a pergunta atual, SEM o histórico anterior
    nova_sessao = [
        {"role": "user", "content": "Qual é o nome do meu projeto e qual "
                                     "stack ele usa?"}
    ]
    resposta = client.messages.create(
        model=MODELS["sonnet"], max_tokens=MAX_TOKENS_DEMO, messages=nova_sessao
    )
    texto = "".join(b.text for b in resposta.content if b.type == "text")
    print("Resposta na nova sessão (sem contexto anterior):")
    print(texto.strip())

    print(
        "\nPonto-chave: como esperado, o modelo não sabe responder — a "
        "informação\nnão foi persistida em lugar nenhum. Se precisássemos "
        "dela entre\nsessões, teríamos que salvá-la fora da janela de "
        "contexto (arquivo de\nestado, banco de dados, memória externa) e "
        "reinjetá-la explicitamente."
    )
    pause()


# ------------------------------------------------------------------------
# 7. SUBAGENT HANDOFFS
# ------------------------------------------------------------------------
def demo_subagent_handoff(client: anthropic.Anthropic):
    """
    Conceito: para tarefas grandes, decompor em subagentes com contexto
    isolado (apenas a tarefa escopada + o que é estritamente necessário) e
    devolver só um resumo ao agente principal. Os passos intermediários do
    subagente não poluem o contexto do agente pai.
    """
    hr("7) SUBAGENT HANDOFF — contexto isolado + resumo de volta")

    tarefa_principal = (
        "Preciso decidir entre PostgreSQL e MongoDB para um novo serviço "
        "de catálogo de produtos com buscas por atributos variáveis."
    )
    print(f"Tarefa do agente principal: {tarefa_principal}\n")

    # --- Subagente 1: pesquisa isolada sobre PostgreSQL ---
    print("--- Subagente A: pesquisa isolada sobre PostgreSQL ---")
    sub_a = client.messages.create(
        model=MODELS["sonnet"],
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                "Você é um subagente com uma única tarefa: liste em até 3 "
                "bullets os prós e contras do PostgreSQL para um catálogo "
                "de produtos com atributos variáveis (schema flexível). "
                "Responda APENAS com o resumo final, sem explicar seu "
                "raciocínio."
            ),
        }],
    )
    resumo_a = "".join(b.text for b in sub_a.content if b.type == "text")
    print(resumo_a.strip(), "\n")

    # --- Subagente 2: pesquisa isolada sobre MongoDB ---
    print("--- Subagente B: pesquisa isolada sobre MongoDB ---")
    sub_b = client.messages.create(
        model=MODELS["sonnet"],
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                "Você é um subagente com uma única tarefa: liste em até 3 "
                "bullets os prós e contras do MongoDB para um catálogo de "
                "produtos com atributos variáveis (schema flexível). "
                "Responda APENAS com o resumo final, sem explicar seu "
                "raciocínio."
            ),
        }],
    )
    resumo_b = "".join(b.text for b in sub_b.content if b.type == "text")
    print(resumo_b.strip(), "\n")

    # --- Agente principal recebe só os resumos, não o processo de pesquisa ---
    print("--- Agente principal: decide com base SÓ nos resumos recebidos ---")
    decisao = client.messages.create(
        model=MODELS["sonnet"],
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Tarefa original: {tarefa_principal}\n\n"
                f"Resumo do subagente A (PostgreSQL):\n{resumo_a}\n\n"
                f"Resumo do subagente B (MongoDB):\n{resumo_b}\n\n"
                "Com base apenas nesses resumos, recomende uma opção em "
                "2 frases."
            ),
        }],
    )
    texto_decisao = "".join(b.text for b in decisao.content if b.type == "text")
    print(texto_decisao.strip())

    print(
        "\nPonto-chave: o contexto do agente principal contém apenas os "
        "DOIS\nresumos finais — não o raciocínio intermediário de cada "
        "subagente. Isso\nmantém o custo por turno baixo, ao preço de "
        "perder visibilidade sobre\ncomo cada subagente chegou à sua "
        "conclusão."
    )
    pause()


# ------------------------------------------------------------------------
# 8. RAG — chunking, embedding match (simulado) e assembly
# ------------------------------------------------------------------------
@dataclass
class Chunk:
    id: int
    texto: str
    origem: str


def _chunk_por_sentenca(texto: str, origem: str, tamanho_alvo: int = 2,
                         overlap: int = 1) -> list:
    """
    Chunking simples baseado em sentenças, com overlap para não cortar
    fatos que atravessam uma fronteira de chunk.
    """
    sentencas = [s.strip() for s in texto.split(".") if s.strip()]
    chunks = []
    passo = max(tamanho_alvo - overlap, 1)
    i = 0
    idx = 0
    while i < len(sentencas):
        grupo = sentencas[i:i + tamanho_alvo]
        if grupo:
            chunks.append(Chunk(idx, ". ".join(grupo) + ".", origem))
            idx += 1
        i += passo
    return chunks


def demo_rag(client: anthropic.Anthropic):
    """
    Conceito: os três pontos onde um pipeline RAG pode falhar:
      (a) chunking — como o texto é dividido em unidades recuperáveis;
      (b) embedding match — busca por similaridade semântica (aqui
          SIMULADA por um match léxico simples, já que uma demo local não
          tem um índice vetorial real);
      (c) assembly — como os chunks recuperados entram no prompt final.
    """
    hr("8) RAG — chunking, 'embedding match' (simulado) e assembly")

    corpus = {
        "politica_reembolso.txt": (
            "Reembolsos são processados em até 5 dias úteis após a "
            "aprovação. O cliente deve solicitar pelo app. Compras acima "
            "de R$500 exigem confirmação por e-mail. Reembolsos em cartão "
            "de crédito podem levar até 2 faturas para aparecer."
        ),
        "politica_troca.txt": (
            "Trocas de produto são aceitas em até 30 dias corridos. O "
            "produto deve estar sem uso e com a embalagem original. Não "
            "há reembolso do frete de devolução em trocas por preferência "
            "do cliente."
        ),
    }

    # (a) CHUNKING
    print("--- (a) Chunking (por sentença, com overlap) ---")
    todos_chunks = []
    for origem, texto in corpus.items():
        chunks = _chunk_por_sentenca(texto, origem)
        todos_chunks.extend(chunks)
        for c in chunks:
            print(f"  [{origem} #{c.id}] {c.texto}")

    # (b) EMBEDDING MATCH — simulado com contagem de palavras em comum
    # (uma demo real usaria um modelo de embeddings + busca vetorial; aqui
    # simplificamos para ilustrar o CONCEITO sem depender de infraestrutura)
    pergunta = "Quanto tempo demora para o reembolso do cartão aparecer?"
    print(f"\n--- (b) 'Embedding match' simulado para: {pergunta!r} ---")

    def score_lexico(pergunta: str, chunk_texto: str) -> int:
        palavras_pergunta = set(pergunta.lower().split())
        palavras_chunk = set(chunk_texto.lower().split())
        return len(palavras_pergunta & palavras_chunk)

    ranqueados = sorted(
        todos_chunks, key=lambda c: score_lexico(pergunta, c.texto),
        reverse=True
    )
    top_k = ranqueados[:2]
    for c in top_k:
        print(f"  score={score_lexico(pergunta, c.texto)} -> "
              f"[{c.origem} #{c.id}] {c.texto}")

    print(
        "\n  Nota: um retriever real usaria embeddings semânticos, não "
        "contagem\n  de palavras — aqui simulamos com match léxico para "
        "ilustrar o conceito\n  sem exigir um índice vetorial na demo. "
        "Isso também ilustra o risco: um\n  match puramente léxico pode "
        "perder sinônimos, e um puramente semântico\n  pode perder termos "
        "exatos — por isso às vezes se combina os dois."
    )

    # (c) ASSEMBLY — os chunks recuperados entram no prompt na estrutura
    # esperada, para o modelo responder com base no texto recuperado,
    # não "de memória".
    print("\n--- (c) Assembly: montando o prompt final com os chunks ---")
    contexto_recuperado = "\n".join(
        f"[Fonte: {c.origem}] {c.texto}" for c in top_k
    )
    prompt_final = (
        "Responda à pergunta do usuário APENAS com base no contexto "
        "abaixo. Cite a fonte entre colchetes.\n\n"
        f"CONTEXTO:\n{contexto_recuperado}\n\n"
        f"PERGUNTA: {pergunta}"
    )
    print("Prompt final enviado ao modelo:")
    print(prompt_final)

    resposta = client.messages.create(
        model=MODELS["sonnet"],
        max_tokens=MAX_TOKENS_DEMO,
        messages=[{"role": "user", "content": prompt_final}],
    )
    texto_resposta = "".join(b.text for b in resposta.content if b.type == "text")
    print("\nResposta do modelo (fundamentada no contexto recuperado):")
    print(texto_resposta.strip())

    print(
        "\nPonto-chave: a resposta final cita a fonte porque o assembly "
        "colocou\nos chunks recuperados na estrutura que o prompt espera — "
        "se a etapa de\nassembly falhar (ex.: chunks soltos sem indicar a "
        "origem), o modelo\ntende a responder de memória em vez de usar o "
        "texto recuperado."
    )
    pause()


# ------------------------------------------------------------------------
# MENU PRINCIPAL
# ------------------------------------------------------------------------
def main():
    client = get_client()

    opcoes = {
        "1": ("Seleção de modelo (Haiku vs Sonnet)", demo_model_selection),
        "2": ("Janela de contexto e token counting", demo_token_counting),
        "3": ("Prompt caching", demo_prompt_caching),
        "4": ("Pruning", demo_pruning),
        "5": ("Compactação (summarizer vago vs. específico)", demo_compaction),
        "6": ("Clearing (nova sessão)", demo_clearing),
        "7": ("Subagent handoffs", demo_subagent_handoff),
        "8": ("RAG: chunking, embedding match e assembly", demo_rag),
    }

    while True:
        hr("MENU — Engenharia de Contexto com a API da Anthropic")
        for chave, (titulo, _) in opcoes.items():
            print(f"  [{chave}] {titulo}")
        print("  [0] Sair")

        escolha = input("\nEscolha uma opção: ").strip()

        if escolha == "0":
            print("Até mais!")
            break

        item = opcoes.get(escolha)
        if not item:
            print("Opção inválida.")
            continue

        _, funcao = item
        try:
            funcao(client)
        except anthropic.APIError as e:
            print(f"\n❌ Erro na chamada à API: {e}")
            pause()


if __name__ == "__main__":
    main()