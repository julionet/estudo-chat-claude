# Chat Interativo com Claude (Anthropic)

Aplicação de chat em terminal que demonstra os principais recursos da API da Anthropic: seleção de modo de resposta (streaming em tempo real ou síncrono com prompt caching), tool use (function calling), gerenciamento de contexto com sumarização automática e contagem de tokens.

---

## Sumário

- [Visão Geral](#visão-geral)
- [Pré-requisitos](#pré-requisitos)
- [Configuração](#configuração)
- [Como Executar](#como-executar)
- [Arquitetura e Fluxo de Execução](#arquitetura-e-fluxo-de-execução)
- [Funcionalidades Detalhadas](#funcionalidades-detalhadas)
  - [1. Seleção de Modo](#1-seleção-de-modo)
  - [2. Chat com Histórico](#2-chat-com-histórico-multi-turn)
  - [3. Modo Streaming](#3-modo-streaming)
  - [4. Modo Sem Streaming com Prompt Caching](#4-modo-sem-streaming-com-prompt-caching)
  - [5. Gerenciamento de Contexto](#5-gerenciamento-de-contexto-e-sumarização-automática)
  - [6. Tool Use](#6-tool-use-function-calling)
  - [7. System Prompt](#7-system-prompt-configurável)
- [Ferramentas Disponíveis](#ferramentas-disponíveis)
  - [buscar_endereco_cep](#buscar_endereco_cep)
  - [somar_produtos_categoria](#somar_produtos_categoria)
- [Dados de Exemplo](#dados-de-exemplo)
- [Constantes e Parâmetros](#constantes-e-parâmetros)
- [Estrutura do Código](#estrutura-do-código)
- [Fluxo de Eventos do Streaming](#fluxo-de-eventos-do-streaming)
- [Tratamento de Erros](#tratamento-de-erros)
- [Dependências](#dependências)

---

## Visão Geral

O projeto é uma aplicação Python de linha de comando que mantém uma conversa contínua com o modelo Claude da Anthropic. Cada mensagem enviada pelo usuário carrega todo o histórico de turnos anteriores, permitindo que o modelo mantenha contexto ao longo da sessão.

A aplicação foi desenvolvida como estudo dos seguintes recursos da API Anthropic:

- **Seleção de modo**: o usuário escolhe, antes da conversa, entre streaming ou síncrono com cache
- **Streaming**: receber e exibir a resposta token a token, em tempo real
- **Prompt caching**: reutilizar tokens de contexto já processados para reduzir latência e custo no modo síncrono
- **Tool use**: permitir que o modelo requisite a execução de funções locais para responder perguntas que dependem de dados externos
- **Contagem de tokens**: monitorar o tamanho do contexto antes de cada requisição
- **Sumarização automática**: comprimir o histórico quando ele se aproxima do limite do modelo

---

## Pré-requisitos

- Python 3.9 ou superior
- Conta na [Anthropic](https://console.anthropic.com/) com uma API Key válida
- Pacotes Python listados em [Dependências](#dependências)

---

## Configuração

1. Clone o repositório e entre na pasta do projeto.

2. Crie o arquivo `.env` com base no exemplo fornecido:

```bash
cp .env.example .env
```

3. Edite o `.env` e preencha a chave da API:

```
ANTHROPIC_API_KEY=sk-ant-...
```

4. Instale as dependências:

```bash
pip install anthropic python-dotenv
```

---

## Como Executar

```bash
python pergunta-simples.py
```

Ao iniciar, a aplicação solicita:

1. **Modo de operação** — streaming (`s`) ou sem streaming com cache (`n`)
2. **System prompt** — opcional; pressione Enter para pular

```
Conversa iniciada. Digite 'exit' para encerrar.

Usar streaming? [s/n]: n
Modo: sem streaming (com cache)

Prompt de sistema (opcional, Enter para pular):

Voce: qual o endereço do CEP 01310-100?
```

Para encerrar a sessão, digite `exit`.

---

## Arquitetura e Fluxo de Execução

```
main()
│
├── selecionar_modo() → usar_streaming (bool)
├── chamar_api = chamar_com_streaming | chamar_sem_streaming
├── Solicita system prompt (opcional)
│
└── Loop principal de turnos
    │
    ├── Lê entrada do usuário
    │
    ├── [se histórico não vazio]
    │   └── count_tokens() → se > 75% do limite → resumir_historico()
    │
    ├── Adiciona mensagem do usuário ao histórico
    │
    ├── count_tokens() → aviso se acima do limite
    │
    └── Loop interno de chamadas à API
        │
        ├── chamar_api(historico, system_prompt)
        │   ├── [streaming]     messages.stream() → eventos brutos → text_delta → print
        │   └── [sem streaming] messages.create() → cache → print completo + info cache
        │
        ├── stop_reason == "max_tokens"
        │   └── avisa, remove última mensagem do histórico, break
        │
        ├── stop_reason == "tool_use"
        │   ├── salva resposta do modelo no histórico
        │   ├── executa cada tool solicitada localmente
        │   ├── adiciona resultados ao histórico como role=user
        │   └── continue (nova chamada à API com os resultados)
        │
        ├── stop_reason == "end_turn"
        │   ├── salva resposta no histórico
        │   └── break (aguarda próximo turno do usuário)
        │
        └── stop_reason inesperado
            └── avisa e break (evita loop infinito)
```

---

## Funcionalidades Detalhadas

### 1. Seleção de Modo

No início da sessão, antes do system prompt, a aplicação pergunta ao usuário qual modo de chamada deseja usar:

```
Usar streaming? [s/n]:
```

- **`s` (streaming)**: a resposta é exibida token a token em tempo real à medida que o modelo gera o texto. Usa `client.messages.stream()`.
- **`n` (sem streaming)**: a chamada é síncrona — aguarda a resposta completa antes de exibir. Usa `client.messages.create()` com prompt caching ativo.

A escolha do modo define qual função (`chamar_com_streaming` ou `chamar_sem_streaming`) será atribuída à variável `chamar_api`, usada em todos os turnos da conversa:

```python
chamar_api = chamar_com_streaming if usar_streaming else chamar_sem_streaming
```

---

### 2. Chat com Histórico (multi-turn)

O histórico é uma lista Python de dicionários no formato da API Anthropic:

```python
historico = [
    {"role": "user",      "content": "Qual o endereço do CEP 01310-100?"},
    {"role": "assistant", "content": [...]},   # pode ser lista de blocos (tool_use)
    {"role": "user",      "content": [...]},   # pode ser lista de tool_result
    {"role": "assistant", "content": "O endereço é Av. Paulista, 1000..."},
]
```

A cada novo turno, a lista completa é enviada para a API no campo `messages`, garantindo que o modelo tenha acesso a todo o contexto da sessão.

Quando o modelo usa uma tool, o histórico registra dois turnos extras obrigatórios para conformidade com o protocolo da API:

1. `role: assistant` com o bloco `tool_use` (a solicitação do modelo)
2. `role: user` com o bloco `tool_result` (o resultado retornado pela aplicação)

---

### 3. Modo Streaming

Implementado em `chamar_com_streaming`. Itera diretamente sobre os eventos brutos do stream para garantir exibição em tempo real sem buffering intermediário:

```python
with client.messages.stream(...) as stream:
    for evento in stream:
        if evento.type == "content_block_delta" and evento.delta.type == "text_delta":
            print(evento.delta.text, end="", flush=True)
            resposta_texto += evento.delta.text

    response = stream.get_final_message()
```

**Por que iterar sobre eventos brutos e não sobre `stream.text_stream`?**

`stream.text_stream` é um iterador de alto nível do SDK que pode bufferizar fragmentos antes de yieldar, especialmente em ambientes Windows. Iterando diretamente sobre `stream`, cada evento `text_delta` é processado e impresso no instante em que chega do socket. O `flush=True` força a descarga imediata do buffer do stdout a cada fragmento.

**Eventos ignorados intencionalmente:**

| Tipo de evento | Tipo de delta | Motivo para ignorar |
|---|---|---|
| `content_block_start` | — | Metadados do bloco; desnecessários para exibição ou tool use |
| `content_block_delta` | `input_json_delta` | Fragmentos do JSON de entrada da tool; o SDK reconstrói o objeto completo e o entrega via `get_final_message()` |
| `content_block_stop` | — | Sinalização de fim de bloco; não usado |
| `message_delta` | — | Metadados da mensagem; `stop_reason` é obtido de `get_final_message()` |

---

### 4. Modo Sem Streaming com Prompt Caching

Implementado em `chamar_sem_streaming`. Usa `client.messages.create()` (chamada síncrona) com o recurso de **prompt caching** da Anthropic para reduzir latência e custo em conversas longas.

#### O que é Prompt Caching

A API Anthropic pode armazenar em cache partes do contexto (system prompt e mensagens) que não mudam entre turnos. Quando o mesmo conteúdo é enviado em requisições subsequentes, a API reutiliza o processamento já feito, reduzindo:

- **Latência**: menos tokens precisam ser processados do zero
- **Custo**: tokens lidos do cache são cobrados a uma tarifa menor

O cache tem duração de **5 minutos** a partir do último uso, renovando-se a cada hit.

#### Como o caching é aplicado

O cache é ativado adicionando `"cache_control": {"type": "ephemeral"}` nos blocos que devem ser cacheados. A aplicação aplica o cache em dois pontos:

**System prompt** — via `construir_system_com_cache`:

```python
[{
    "type": "text",
    "text": "Você é um assistente...",
    "cache_control": {"type": "ephemeral"}
}]
```

**Última mensagem do histórico** — via `construir_mensagens_com_cache`:

```python
# se o conteúdo for string, converte para bloco com cache:
[{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}]

# se o conteúdo já for lista de blocos, adiciona cache_control ao último bloco
```

O cache é marcado sempre na **última mensagem**, que representa o ponto de fronteira mais recente do contexto estável. A cada turno, o ponto de cache avança — o histórico até a mensagem anterior já está cacheado; apenas a nova mensagem é processada do zero.

> A função `construir_mensagens_com_cache` **nunca muta o histórico original** — ela retorna uma cópia com as modificações, preservando a integridade da lista `historico` usada pelo loop principal.

#### Exibição das informações de cache

Após cada resposta no modo sem streaming, a aplicação exibe os tokens de cache utilizados:

```
Claude: O endereço do CEP 01310-100 é Av. Paulista, 1000 - Bela Vista, São Paulo - SP.
  [cache — criados: 312 tokens, lidos: 0 tokens]
```

- **criados**: tokens gravados no cache neste turno (primeiro acesso ao contexto)
- **lidos**: tokens recuperados do cache (turnos subsequentes com o mesmo contexto)

---

### 5. Gerenciamento de Contexto e Sumarização Automática

Modelos de linguagem têm um limite de tokens no contexto. Esta aplicação usa dois mecanismos para gerenciar isso.

#### Contagem de tokens

Antes de cada requisição, a aplicação conta os tokens do histórico atual:

```python
contagem = client.messages.count_tokens(
    model=MODEL,
    system=system_prompt,
    messages=historico
)
```

Isso usa a API de contagem da Anthropic, que retorna o número exato de tokens que seriam consumidos na requisição.

#### Sumarização automática (`resumir_historico`)

Quando o histórico ultrapassa **75% do limite** (`LIMITE_TOKENS * LIMIAR_RESUMO = 3072 tokens`), a função `resumir_historico()` é chamada **antes** de adicionar a nova mensagem do usuário.

O processo de sumarização:

1. Separa o histórico em duas partes:
   - **Antigos**: todos os turnos exceto os `MENSAGENS_RECENTES` últimos (4 turnos)
   - **Recentes**: os 4 últimos turnos, mantidos intactos

2. Envia os turnos antigos ao Claude com a instrução de resumi-los:

```python
system=(
    "Resuma a conversa abaixo de forma concisa, preservando fatos, decisões "
    "e contexto necessário para dar continuidade à conversa. Não invente informação."
)
```

3. Tenta até 3 vezes obter um resumo não vazio. Se todas as tentativas falharem, o histórico original é mantido.

4. Substitui os turnos antigos por dois turnos sintéticos:

```python
[
    {"role": "user",      "content": "[Resumo da conversa anterior]: <texto do resumo>"},
    {"role": "assistant", "content": "Entendido, vou considerar esse contexto."},
    # + os 4 turnos recentes originais
]
```

**Por que preservar os turnos recentes?**

Os turnos mais recentes são os mais relevantes para a continuidade imediata da conversa. Comprimi-los perderia o contexto imediato que o usuário acabou de estabelecer.

---

### 6. Tool Use (Function Calling)

Tool use é o mecanismo pelo qual o modelo pode requisitar a execução de funções definidas na aplicação para responder perguntas que dependem de dados externos.

#### Ciclo completo de tool use

```
Usuário pergunta algo
    ↓
Modelo analisa → decide usar uma tool
    ↓
stop_reason = "tool_use" (não é "end_turn")
    ↓
Aplicação lê response.content → encontra bloco tool_use
    ↓
Executa a função local com os argumentos fornecidos pelo modelo
    ↓
Adiciona o resultado ao histórico como role=user / type=tool_result
    ↓
Nova chamada à API com o histórico atualizado
    ↓
Modelo recebe o resultado e gera a resposta final
    ↓
stop_reason = "end_turn"
```

#### Estrutura do loop interno

O loop interno `while True` existe exatamente para suportar esse ciclo: o modelo pode solicitar uma ou mais tools em sequência antes de gerar a resposta final. Cada iteração do loop é uma chamada à API — ambos os modos (streaming e sem streaming) percorrem o mesmo loop.

#### Registro no histórico

```python
# 1. Salva a requisição do modelo (obrigatório pela API)
historico.append({"role": "assistant", "content": response.content})

# 2. Salva o resultado da tool (obrigatório pela API)
historico.append({
    "role": "user",
    "content": [
        {
            "type": "tool_result",
            "tool_use_id": bloco.id,   # vincula ao bloco tool_use do modelo
            "content": json.dumps(resultado, ensure_ascii=False)
        }
    ]
})
```

O `tool_use_id` vincula o resultado à requisição específica do modelo, garantindo rastreabilidade quando múltiplas tools são chamadas no mesmo turno.

---

### 7. System Prompt Configurável

No início de cada sessão, o usuário pode definir um prompt de sistema que guia o comportamento do Claude durante toda a conversa:

```
Prompt de sistema (opcional, Enter para pular): Você é um assistente especializado em e-commerce brasileiro.
```

No modo streaming, o prompt é enviado como string no campo `system`. No modo sem streaming, ele é convertido para o formato de lista com `cache_control` pela função `construir_system_com_cache`, habilitando o cache sobre ele.

---

## Ferramentas Disponíveis

### `buscar_endereco_cep`

Consulta o endereço correspondente a um CEP em uma base fictícia pré-carregada em memória.

**Parâmetro de entrada:**

| Campo | Tipo | Descrição | Exemplo |
|---|---|---|---|
| `cep` | string | CEP no formato com hífen | `"01310-100"` |

**Retorno — sucesso:**

```json
{
    "cep": "01310-100",
    "endereco": "Av. Paulista, 1000 - Bela Vista, São Paulo - SP"
}
```

**Retorno — CEP não encontrado:**

```json
{
    "erro": "CEP 99999-999 não encontrado na base."
}
```

---

### `somar_produtos_categoria`

Calcula o valor total dos produtos de uma categoria na base fictícia e retorna a lista de produtos encontrados.

**Parâmetro de entrada:**

| Campo | Tipo | Descrição | Exemplo |
|---|---|---|---|
| `categoria` | string | Nome da categoria (case-insensitive) | `"Eletrônicos"` |

**Retorno — sucesso:**

```json
{
    "categoria": "Eletrônicos",
    "quantidade_produtos": 3,
    "total": 5850.00,
    "produtos": ["Notebook", "Smartphone", "Fone de Ouvido"]
}
```

**Retorno — categoria não encontrada:**

```json
{
    "erro": "Nenhum produto encontrado para a categoria 'Ferramentas'."
}
```

---

## Dados de Exemplo

### CEPs cadastrados

| CEP | Endereço |
|---|---|
| 01310-100 | Av. Paulista, 1000 - Bela Vista, São Paulo - SP |
| 20040-020 | Rua da Assembleia, 10 - Centro, Rio de Janeiro - RJ |
| 30130-010 | Av. Afonso Pena, 1500 - Centro, Belo Horizonte - MG |
| 40010-000 | Rua Chile, 20 - Centro, Salvador - BA |
| 50030-230 | Av. Conde da Boa Vista, 500 - Boa Vista, Recife - PE |
| 60060-170 | Av. Santos Dumont, 300 - Aldeota, Fortaleza - CE |
| 70040-010 | Esplanada dos Ministérios, 1 - Brasília - DF |
| 80010-000 | Rua XV de Novembro, 100 - Centro, Curitiba - PR |
| 90010-000 | Av. Borges de Medeiros, 400 - Centro Histórico, Porto Alegre - RS |
| 13010-050 | Rua Barão de Jaguara, 200 - Centro, Campinas - SP |

### Produtos cadastrados

| Produto | Categoria | Valor |
|---|---|---|
| Notebook | Eletrônicos | R$ 3.500,00 |
| Smartphone | Eletrônicos | R$ 2.200,00 |
| Fone de Ouvido | Eletrônicos | R$ 150,00 |
| Camiseta | Vestuário | R$ 60,00 |
| Calça Jeans | Vestuário | R$ 120,00 |
| Tênis | Vestuário | R$ 250,00 |
| Arroz 5kg | Alimentos | R$ 25,00 |
| Feijão 1kg | Alimentos | R$ 8,00 |
| Café 500g | Alimentos | R$ 15,00 |
| Sofá 3 Lugares | Móveis | R$ 1.800,00 |

---

## Constantes e Parâmetros

| Constante | Valor | Descrição |
|---|---|---|
| `MODEL` | `claude-haiku-4-5-20251001` | Modelo Claude usado em todas as requisições |
| `LIMITE_TOKENS` | `4096` | Limite máximo de tokens por requisição |
| `LIMIAR_RESUMO` | `0.75` | Fração do limite que dispara a sumarização (3072 tokens) |
| `MENSAGENS_RECENTES` | `4` | Número de turnos recentes preservados intactos na sumarização |

---

## Estrutura do Código

```
pergunta-simples.py
│
├── Constantes de configuração
│   ├── MODEL, LIMITE_TOKENS, LIMIAR_RESUMO, MENSAGENS_RECENTES
│   ├── CEPS_FICTICIOS             — dict com 10 CEPs brasileiros fictícios
│   ├── PRODUTOS_FICTICIOS         — lista com 10 produtos em 4 categorias
│   └── TOOLS                      — definição das tools no formato da API Anthropic
│
├── buscar_endereco_cep(cep)
│   └── Consulta CEPS_FICTICIOS e retorna endereço ou erro
│
├── somar_produtos_categoria(categoria)
│   └── Filtra PRODUTOS_FICTICIOS por categoria e soma os valores
│
├── executar_tool(nome, entrada)
│   └── Dispatcher: roteia pelo nome da tool para a função correspondente
│
├── resumir_historico(historico)
│   └── Comprime turnos antigos via API, preserva os mais recentes
│
├── selecionar_modo()
│   └── Pergunta s/n e retorna bool (True = streaming)
│
├── construir_system_com_cache(system_prompt)
│   └── Converte string → lista com cache_control para o modo sem streaming
│
├── construir_mensagens_com_cache(historico)
│   └── Retorna cópia do histórico com cache_control na última mensagem
│
├── chamar_com_streaming(historico, system_prompt)
│   └── messages.stream() → eventos brutos → text_delta → print em tempo real
│
├── chamar_sem_streaming(historico, system_prompt)
│   └── messages.create() com cache → print completo + exibe uso de cache
│
└── main()
    └── Seleciona modo, define chamar_api, loop de turnos com gerenciamento de contexto
```

---

## Fluxo de Eventos do Streaming

A API Anthropic envia uma sequência de eventos Server-Sent Events (SSE) durante o streaming. A tabela abaixo descreve cada tipo e como a aplicação os trata:

| Evento | Campo relevante | Tratamento na aplicação |
|---|---|---|
| `message_start` | — | Ignorado |
| `content_block_start` | `content_block.type` | Ignorado |
| `content_block_delta` | `delta.type == "text_delta"` | Imprime `delta.text` imediatamente com `flush=True` |
| `content_block_delta` | `delta.type == "input_json_delta"` | Ignorado — SDK reconstrói o JSON internamente |
| `content_block_stop` | — | Ignorado |
| `message_delta` | `delta.stop_reason` | Ignorado — lido via `get_final_message()` |
| `message_stop` | — | Sinaliza fim do stream; `get_final_message()` retorna |

---

## Tratamento de Erros

| Situação | Comportamento |
|---|---|
| Entrada inválida na seleção de modo | Solicita nova entrada até receber `s` ou `n` |
| `stop_reason == "max_tokens"` | Exibe aviso, remove a última mensagem do histórico (evita turno incompleto) e encerra o turno |
| `stop_reason` desconhecido | Exibe aviso com o valor recebido, remove a última mensagem do histórico e encerra o turno via `break`, evitando loop infinito |
| Resumo vazio após 3 tentativas | Mantém o histórico original sem sumarizar e exibe aviso |
| Tool não reconhecida | `executar_tool` retorna `{"erro": "Tool '...' não reconhecida."}` e o modelo recebe esse erro como resultado |
| CEP não encontrado | Retorna `{"erro": "CEP ... não encontrado na base."}` |
| Categoria não encontrada | Retorna `{"erro": "Nenhum produto encontrado para a categoria '...'."}` |

---

## Dependências

| Pacote | Finalidade |
|---|---|
| `anthropic` | SDK oficial da Anthropic para acesso à API Claude |
| `python-dotenv` | Carregamento de variáveis de ambiente a partir do arquivo `.env` |
