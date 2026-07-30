#!/usr/bin/env python3
"""
Demonstracao pratica: Memory Scope, Skills e padroes de agentes
=================================================================

Aplicacao de linha de comando que exemplifica, com chamadas REAIS a API da
Anthropic, os conceitos do capitulo:

  1. Memoria em Contexto (in-context memory)
  2. Armazenamento Externo (external storage)
  3. Memoria Sumarizada (summarized memory)
  4. Sem Memoria Persistente (stateless)
  5. Skills (SKILL.md) - carregamento sob demanda vs CLAUDE.md sempre ativo
  6. Skills via Messages API (beta) - chamada real usando Agent Skills

Requisitos:
    pip install anthropic --break-system-packages
    export ANTHROPIC_API_KEY="sua-chave-aqui"

Uso:
    python3 app.py
"""

import os
import re
import sys
import json
import sqlite3
import textwrap
from datetime import datetime
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("Pacote 'anthropic' nao encontrado.")
    print("Instale com: pip install anthropic --break-system-packages")
    sys.exit(1)

# --------------------------------------------------------------------------
# Configuracao geral
# --------------------------------------------------------------------------

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
DB_PATH = Path(__file__).parent / "external_storage.db"
SKILLS_DIR = Path(__file__).parent / "skills_local"

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    print("AVISO: variavel ANTHROPIC_API_KEY nao encontrada no ambiente.")
    print("Defina com: export ANTHROPIC_API_KEY='sua-chave-aqui'")
    print("A aplicacao vai abrir, mas as chamadas de API vao falhar ate a chave ser configurada.\n")

client = Anthropic(api_key=API_KEY) if API_KEY else None


def call_claude(messages, system=None, max_tokens=500):
    """Wrapper simples para uma chamada de mensagem, com tratamento de erro."""
    if client is None:
        return "[ERRO] ANTHROPIC_API_KEY nao configurada. Defina a variavel de ambiente e reinicie."
    try:
        kwargs = {
            "model": MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        return "".join(block.text for block in response.content if block.type == "text")
    except Exception as exc:
        return f"[ERRO na chamada da API] {exc}"


def approx_tokens(messages):
    """Estimativa grosseira de tokens (~4 caracteres por token) so para fins didaticos."""
    total_chars = sum(len(m["content"]) for m in messages if isinstance(m["content"], str))
    return total_chars // 4


def header(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def pause():
    input("\n[Enter para voltar ao menu]")


# --------------------------------------------------------------------------
# 1. MEMORIA EM CONTEXTO (in-context memory)
# --------------------------------------------------------------------------

def demo_in_context_memory():
    header("1. MEMORIA EM CONTEXTO (in-context)")
    print(textwrap.dedent("""
        Conceito: o historico inteiro da conversa fica na lista `messages` e e
        reenviado a CADA chamada de API. Custo zero de "busca" (nao ha banco
        de dados), mas o custo de TOKENS cresce a cada turno, porque o modelo
        releh tudo de novo. Ao encerrar o script, TUDO se perde -- nada e
        salvo em disco.
    """))
    print("Digite mensagens para conversar. Digite 'sair' para encerrar este demo.\n")

    messages = []
    while True:
        user_input = input("Voce: ").strip()
        if user_input.lower() in ("sair", "exit", "quit"):
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        reply = call_claude(messages)
        messages.append({"role": "assistant", "content": reply})

        print(f"Claude: {reply}")
        print(f"   (contexto atual: {len(messages)} mensagens, "
              f"~{approx_tokens(messages)} tokens estimados)\n")

    print("\nFim da sessao -- este historico NAO foi salvo em lugar nenhum.")
    print("Se voce rodar o script de novo, o Claude nao vai lembrar de nada disso.")
    pause()


# --------------------------------------------------------------------------
# 2. ARMAZENAMENTO EXTERNO (external storage)
# --------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def demo_external_storage():
    header("2. ARMAZENAMENTO EXTERNO (external storage)")
    print(textwrap.dedent(f"""
        Conceito: o estado da conversa e gravado em um banco de dados
        (aqui, SQLite em '{DB_PATH.name}') e lido de volta no INICIO da
        sessao. Isso permite que o agente "lembre" de voce mesmo depois de
        fechar e reabrir o programa -- o preco e a latencia de cada leitura
        e a logica extra de leitura/escrita.

        Experimente: converse, feche o script (Ctrl+C ou 'sair'), rode de
        novo e use o MESMO session_id -- o historico volta.
    """))

    session_id = input("Informe um session_id (ex: 'jose-01'): ").strip() or "default"
    conn = init_db()

    # 1) Recupera memoria de sessoes anteriores (simulando "novo processo")
    cursor = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY rowid",
        (session_id,),
    )
    history = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]

    if history:
        print(f"\n[Memoria recuperada do banco: {len(history)} mensagens de sessoes anteriores]")
        for m in history[-4:]:
            print(f"   {m['role']}: {m['content'][:80]}")
    else:
        print("\n[Nenhuma memoria anterior encontrada para este session_id -- comecando do zero]")

    print("\nDigite mensagens. Digite 'sair' para encerrar (o historico fica salvo).\n")

    while True:
        user_input = input("Voce: ").strip()
        if user_input.lower() in ("sair", "exit", "quit"):
            break
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?)",
            (session_id, "user", user_input, datetime.utcnow().isoformat()),
        )

        reply = call_claude(history)
        history.append({"role": "assistant", "content": reply})
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?)",
            (session_id, "assistant", reply, datetime.utcnow().isoformat()),
        )
        conn.commit()

        print(f"Claude: {reply}\n")

    conn.close()
    print(f"Sessao encerrada. Historico gravado em '{DB_PATH}' sob session_id='{session_id}'.")
    print("Rode este demo de novo com o mesmo session_id para ver a memoria persistir.")
    pause()


# --------------------------------------------------------------------------
# 3. MEMORIA SUMARIZADA (summarized memory)
# --------------------------------------------------------------------------

def demo_summarized_memory():
    header("3. MEMORIA SUMARIZADA (summarized memory)")
    print(textwrap.dedent("""
        Conceito: em vez de reenviar o historico completo, a cada N turnos
        pedimos ao proprio Claude para CONDENSAR a conversa em um resumo
        curto. Esse resumo (nao o historico bruto) e o que carregamos para
        frente. Economiza tokens a longo prazo, mas qualquer detalhe que o
        resumo nao preservar e perdido para sempre.
    """))

    SUMMARIZE_EVERY = 3  # turnos completos (user+assistant) antes de resumir
    full_history = []
    summary = None
    turns_since_summary = 0

    print(f"A cada {SUMMARIZE_EVERY} turnos, o historico sera resumido automaticamente.")
    print("Digite mensagens. Digite 'sair' para encerrar.\n")

    while True:
        user_input = input("Voce: ").strip()
        if user_input.lower() in ("sair", "exit", "quit"):
            break
        if not user_input:
            continue

        # Monta o contexto real enviado: resumo (se existir) + turnos recentes
        messages_to_send = list(full_history)
        messages_to_send.append({"role": "user", "content": user_input})

        system_prompt = None
        if summary:
            system_prompt = f"Contexto resumido da conversa ate agora: {summary}"

        reply = call_claude(messages_to_send, system=system_prompt)

        full_history.append({"role": "user", "content": user_input})
        full_history.append({"role": "assistant", "content": reply})
        turns_since_summary += 1

        print(f"Claude: {reply}")
        tokens_sem_resumo = approx_tokens(full_history)
        print(f"   (turnos desde o ultimo resumo: {turns_since_summary} | "
              f"tokens do historico bruto acumulado: ~{tokens_sem_resumo})\n")

        if turns_since_summary >= SUMMARIZE_EVERY:
            print("   >> Resumindo conversa para liberar contexto...")
            summarization_prompt = [{
                "role": "user",
                "content": (
                    "Resuma a conversa abaixo em no maximo 3 frases, "
                    "preservando fatos e decisoes importantes:\n\n"
                    + "\n".join(f"{m['role']}: {m['content']}" for m in full_history)
                ),
            }]
            summary = call_claude(summarization_prompt, max_tokens=200)
            print(f"   >> Resumo gerado: {summary}\n")

            # A partir daqui, o historico bruto e descartado -- so o resumo
            # (via system prompt) segue para os proximos turnos.
            full_history = []
            turns_since_summary = 0

    print("\nFim da sessao. Note como o 'tokens do historico bruto' zera apos cada resumo,")
    print("enquanto na memoria em contexto (opcao 1) ele so cresce.")
    pause()


# --------------------------------------------------------------------------
# 4. SEM MEMORIA PERSISTENTE (stateless)
# --------------------------------------------------------------------------

def demo_stateless():
    header("4. SEM MEMORIA PERSISTENTE (stateless)")
    print(textwrap.dedent("""
        Conceito: cada chamada e completamente independente. Nenhum
        historico e guardado, nem mesmo dentro da mesma "sessao" do menu.
        Ideal para agentes que executam UMA tarefa e encerram (ex: pipeline
        que classifica um texto e termina).

        Vamos fazer duas perguntas em sequencia para voce ver, na pratica,
        que a segunda chamada NAO tem ideia do que foi perguntado na primeira.
    """))

    pergunta1 = input("Pergunta 1 (ex: 'Meu nome e Jose, guarde isso'): ").strip()
    if pergunta1:
        resposta1 = call_claude([{"role": "user", "content": pergunta1}])
        print(f"Claude: {resposta1}\n")

    pergunta2 = input("Pergunta 2 (ex: 'Qual e o meu nome?'): ").strip()
    if pergunta2:
        # Note: enviamos APENAS a pergunta 2, sem nenhum historico da pergunta 1.
        resposta2 = call_claude([{"role": "user", "content": pergunta2}])
        print(f"Claude: {resposta2}\n")

    print("Repare que a segunda resposta nao tem acesso ao que foi dito na primeira,")
    print("porque cada chamada aqui e enviada isoladamente -- sem historico algum.")
    pause()


# --------------------------------------------------------------------------
# 5. SKILLS (SKILL.md) - carregamento sob demanda, comparado a CLAUDE.md
# --------------------------------------------------------------------------

def load_local_skills():
    """Le todos os SKILL.md em skills_local/ e extrai name/description/conteudo."""
    skills = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        text = skill_file.read_text(encoding="utf-8")
        # frontmatter simples entre --- e ---
        parts = text.split("---")
        frontmatter = parts[1] if len(parts) >= 3 else ""
        body = "---".join(parts[2:]) if len(parts) >= 3 else text

        name, description = skill_dir.name, ""
        for line in frontmatter.strip().splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            if line.startswith("description:"):
                description = line.split(":", 1)[1].strip()

        skills.append({"name": name, "description": description, "body": body.strip()})
    return skills


def match_skill(user_request, skills):
    """Matching local simples por sobreposicao de palavras-chave.

    Isso imita, de forma simplificada, o que o Claude faz de verdade:
    comparar a descricao de cada Skill contra o pedido do usuario e so
    carregar o conteudo completo quando ha correspondencia.
    """
    request_words = set(re.findall(r"[a-z0-9]+", user_request.lower()))
    best_skill, best_score = None, 0
    for skill in skills:
        desc_words = set(re.findall(r"[a-z0-9]+", skill["description"].lower()))
        score = len(request_words & desc_words)
        if score > best_score:
            best_skill, best_score = skill, score
    return best_skill if best_score > 0 else None


# Instrucao "estilo CLAUDE.md": sempre carregada, custo fixo por sessao,
# independente da tarefa -- usada aqui so para efeito de COMPARACAO.
ALWAYS_ON_INSTRUCTIONS = (
    "Responda sempre em portugues do Brasil, em tom profissional e conciso, "
    "usando no maximo 3 paragrafos."
)


def demo_skills_local():
    header("5. SKILLS (SKILL.md) vs CLAUDE.md (comparacao de custo de contexto)")
    skills = load_local_skills()

    print(textwrap.dedent(f"""
        Foram carregados {len(skills)} Skills de '{SKILLS_DIR.name}/' (so nome + descricao,
        ~{sum(approx_tokens([{'content': s['description']}]) for s in skills)} tokens estimados neste momento):
    """))
    for s in skills:
        print(f"  - {s['name']}: {s['description'][:90]}...")

    print(textwrap.dedent("""
        Ao contrario de um CLAUDE.md (que carregaria suas instrucoes completas em
        TODA sessao, dando ou nao match com a tarefa), aqui o conteudo COMPLETO de
        um Skill so entra no prompt quando a descricao bate com o seu pedido.
    """))

    user_request = input("\nFaca um pedido (ex: 'revisar codigo: def soma(a,b): return a+b'): ").strip()
    if not user_request:
        pause()
        return

    matched = match_skill(user_request, skills)

    if matched:
        print(f"\n[Skill correspondente encontrado: '{matched['name']}' -> carregando instrucoes completas]")
        system_prompt = (
            f"{ALWAYS_ON_INSTRUCTIONS}\n\n"
            f"Instrucoes do Skill '{matched['name']}' (carregadas sob demanda):\n{matched['body']}"
        )
        tokens_extra = approx_tokens([{"content": matched["body"]}])
        print(f"   (custo extra de contexto deste Skill: ~{tokens_extra} tokens, so nesta chamada)")
    else:
        print("\n[Nenhum Skill correspondeu -- nenhuma instrucao extra sera carregada]")
        system_prompt = ALWAYS_ON_INSTRUCTIONS

    reply = call_claude([{"role": "user", "content": user_request}], system=system_prompt)
    print(f"\nClaude: {reply}")

    print(textwrap.dedent("""
        Compare: se isso fosse um CLAUDE.md, as instrucoes completas de TODOS os
        Skills estariam presentes em TODA chamada, dando match ou nao -- inflando
        o contexto de tarefas que nao precisam delas.
    """))
    pause()


# --------------------------------------------------------------------------
# 6. SKILLS via Messages API (beta) - chamada real usando Agent Skills
# --------------------------------------------------------------------------

def demo_skills_api_beta():
    header("6. SKILLS VIA MESSAGES API (beta oficial da Anthropic)")
    print(textwrap.dedent("""
        Conceito: a Messages API tem um recurso oficial de Agent Skills (beta).
        Skills invocados assim rodam DENTRO do container de execucao de codigo,
        nao no ambiente da sua aplicacao. Sao necessarios os headers/betas:

            betas=["code-execution-2025-08-25", "skills-2025-10-02"]

        e o parametro `container={"skills": [...]}` apontando para um Skill
        (gerenciado pela Anthropic, como 'pptx', 'xlsx', 'docx', 'pdf', ou um
        Skill customizado enviado via Skills API).

        Este demo faz uma chamada REAL usando o Skill gerenciado 'pptx' para
        gerar uma pequena apresentacao, so para voce ver a resposta chegando
        com file_id (que precisaria da Files API para ser baixado).
    """))

    if client is None:
        print("[ERRO] ANTHROPIC_API_KEY nao configurada -- nao e possivel chamar a API.")
        pause()
        return

    confirm = input("Fazer uma chamada REAL de API usando o Skill 'pptx'? (s/n): ").strip().lower()
    if confirm != "s":
        print("Chamada cancelada pelo usuario.")
        pause()
        return

    tema = input("Tema da mini apresentacao (ex: 'energia solar'): ").strip() or "energia solar"

    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4096,
            betas=["code-execution-2025-08-25", "skills-2025-10-02"],
            container={
                "skills": [{"type": "anthropic", "skill_id": "pptx", "version": "latest"}]
            },
            messages=[
                {"role": "user", "content": f"Crie uma apresentacao de 3 slides sobre {tema}"}
            ],
            tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
        )
        print("\n[Resposta bruta recebida da API -- blocos de conteudo:]")
        for block in response.content:
            print(f"  - tipo: {block.type}")
            if block.type == "text":
                print(f"    texto: {block.text[:300]}")
        print(textwrap.dedent("""
            Se algum bloco tiver 'file_id', esse e o arquivo .pptx gerado pelo Skill
            dentro do container -- para baixa-lo de verdade seria necessario chamar
            a Files API com esse file_id (nao feito aqui, para manter o demo simples).
        """))
    except Exception as exc:
        print(f"[ERRO na chamada beta] {exc}")
        print(textwrap.dedent("""
            Dica: essa e uma API beta, os nomes de header/tool podem mudar. Confira
            sempre a documentacao oficial antes de usar em producao:
            https://platform.claude.com/docs/en/agents-and-tools/agent-skills/quickstart
        """))

    print(textwrap.dedent("""
        Lembrete importante do capitulo: se voce delegasse essa tarefa a um SUBAGENTE,
        ele NAO herdaria este Skill automaticamente -- precisaria ser listado
        explicitamente na configuracao do subagente (embora o escopo de permissoes
        do agente pai seja herdado normalmente).
    """))
    pause()


# --------------------------------------------------------------------------
# MENU PRINCIPAL
# --------------------------------------------------------------------------

MENU_OPTIONS = {
    "1": ("Memoria em Contexto (in-context)", demo_in_context_memory),
    "2": ("Armazenamento Externo (external storage)", demo_external_storage),
    "3": ("Memoria Sumarizada (summarized memory)", demo_summarized_memory),
    "4": ("Sem Memoria Persistente (stateless)", demo_stateless),
    "5": ("Skills (SKILL.md) vs CLAUDE.md", demo_skills_local),
    "6": ("Skills via Messages API (beta, chamada real)", demo_skills_api_beta),
}


def print_menu():
    print("\n" + "#" * 70)
    print("  DEMO: Memory Scope & Skills -- Certificacao Claude Developer")
    print("#" * 70)
    for key, (label, _) in MENU_OPTIONS.items():
        print(f"  [{key}] {label}")
    print("  [0] Sair")


def main():
    while True:
        print_menu()
        choice = input("\nEscolha uma opcao: ").strip()
        if choice == "0":
            print("Ate a proxima!")
            break
        option = MENU_OPTIONS.get(choice)
        if option:
            _, func = option
            func()
        else:
            print("Opcao invalida, tente novamente.")


if __name__ == "__main__":
    main()