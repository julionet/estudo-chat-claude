#!/usr/bin/env python3
"""
claude_multimodal_batch_examples.py

Aplicação didática (arquivo único) que exemplifica, na prática, os
conceitos do módulo "Images, PDFs, and high-volume processing" da
documentação de certificação developer do Claude:

  1. Custo de tokens de imagem (cálculo local)
  2. Envio de imagem via Base64 inline
  3. Envio de imagem via URL
  4. Envio via Files API (upload único + reuso)
  5. Envio de PDF (bloco "document")
  6. Prompting aplicado a imagens (tratando ambiguidade visual)
  7. Message Batches API (processamento assíncrono em lote)
  8. Combinando multimodal + batch (e os erros comuns a evitar)

Requer a variável de ambiente ANTHROPIC_API_KEY para os exemplos
que fazem chamadas reais à API (todos, exceto o item 1).

Instalação:
    pip install anthropic Pillow

Uso:
    export ANTHROPIC_API_KEY="sua-chave-aqui"
    python3 claude_multimodal_batch_examples.py
"""

import base64
import math
import os
import sys
import time

MODEL = "claude-sonnet-4-6"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)
SAMPLE_IMAGE_PATH = os.path.join(ASSETS_DIR, "sample.jpg")
SAMPLE_PDF_PATH = os.path.join(ASSETS_DIR, "sample.pdf")

# Troque por uma URL de imagem pública e acessível para testar o Exemplo 3
# de verdade (o valor abaixo é só ilustrativo).
URL_IMAGEM_EXEMPLO = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/JPEG_example_flower.jpg/640px-JPEG_example_flower.jpg"

_client = None


# =====================================================================
# Utilitários compartilhados
# =====================================================================

def print_header(titulo: str):
    print("\n" + "=" * 70)
    print(titulo)
    print("=" * 70)


def get_client():
    """Retorna um client Anthropic pronto para uso, ou None (com aviso)
    caso ANTHROPIC_API_KEY não esteja configurada."""
    global _client

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "\n[AVISO] Variável de ambiente ANTHROPIC_API_KEY não encontrada.\n"
            "Configure-a antes de rodar exemplos que chamam a API real, ex.:\n"
            "  export ANTHROPIC_API_KEY='sua-chave-aqui'\n"
        )
        return None

    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()

    return _client


def calcular_tokens_imagem(largura: int, altura: int) -> int:
    """
    Fórmula da documentação: Claude enxerga imagens em patches de
    28x28 pixels. tokens = ceil(largura / 28) * ceil(altura / 28)
    """
    return math.ceil(largura / 28) * math.ceil(altura / 28)


def get_image_dimensions(path: str):
    from PIL import Image
    with Image.open(path) as img:
        return img.width, img.height


def garantir_imagem_exemplo() -> str:
    """Gera localmente uma imagem de exemplo (formas geométricas coloridas),
    caso ainda não exista, para uso nos exemplos de envio de imagem.
    Gerar localmente evita depender de acesso a hosts externos."""
    if not os.path.exists(SAMPLE_IMAGE_PATH):
        from PIL import Image, ImageDraw

        print("Gerando imagem de exemplo localmente...")
        img = Image.new("RGB", (640, 480), color=(245, 245, 245))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 640, 300], fill=(135, 206, 235))       # céu
        draw.rectangle([0, 300, 640, 480], fill=(34, 139, 34))       # chão
        draw.ellipse([500, 40, 580, 120], fill=(255, 215, 0))        # sol
        draw.ellipse([80, 200, 200, 320], fill=(0, 100, 0))          # árvore 1
        draw.rectangle([130, 300, 150, 360], fill=(101, 67, 33))
        draw.ellipse([150, 220, 260, 330], fill=(34, 139, 34))       # árvore 2 (sobrepõe a 1)
        draw.rectangle([195, 310, 215, 370], fill=(101, 67, 33))
        draw.ellipse([300, 380, 340, 420], fill=(255, 0, 100))       # flor em 1º plano
        draw.rectangle([317, 420, 323, 460], fill=(0, 128, 0))
        img.save(SAMPLE_IMAGE_PATH, "JPEG", quality=90)
    return SAMPLE_IMAGE_PATH


def _criar_pdf_simples(caminho: str, texto: str):
    """Cria um PDF minimalista, válido, escrevendo os bytes manualmente
    (evita depender de bibliotecas externas de geração de PDF)."""
    linhas = []
    for paragrafo in texto.split("\n"):
        while len(paragrafo) > 90:
            linhas.append(paragrafo[:90])
            paragrafo = paragrafo[90:]
        linhas.append(paragrafo)

    comandos_texto = ["BT", "/F1 14 Tf", "50 750 Td", "16 TL"]
    for linha in linhas:
        linha_escapada = linha.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        comandos_texto.append(f"({linha_escapada}) Tj")
        comandos_texto.append("T*")
    comandos_texto.append("ET")
    stream_conteudo = "\n".join(comandos_texto).encode("latin-1", errors="replace")

    objetos = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(len(stream_conteudo)).encode() + b" >>\nstream\n"
        + stream_conteudo + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    with open(caminho, "wb") as f:
        f.write(b"%PDF-1.4\n")
        offsets = [0]
        pos = len(b"%PDF-1.4\n")
        for obj in objetos:
            offsets.append(pos)
            f.write(obj)
            pos += len(obj)
        xref_start = pos
        f.write(f"xref\n0 {len(objetos)+1}\n".encode())
        f.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            f.write(f"{off:010d} 00000 n \n".encode())
        f.write(
            f"trailer\n<< /Size {len(objetos)+1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF".encode()
        )


def garantir_pdf_exemplo() -> str:
    """Gera localmente um PDF de exemplo simples (texto), caso ainda não
    exista, para uso no exemplo de envio de documento."""
    if not os.path.exists(SAMPLE_PDF_PATH):
        print("Gerando PDF de exemplo localmente...")
        conteudo = (
            "Relatorio de Exemplo\n\n"
            "Este e um documento PDF gerado para demonstrar o envio de "
            "arquivos via bloco 'document' da API do Claude.\n\n"
            "Ele contem um resumo ficticio de vendas do trimestre: "
            "as vendas cresceram 12 por cento em relacao ao trimestre "
            "anterior, impulsionadas principalmente pela regiao Sudeste."
        )
        _criar_pdf_simples(SAMPLE_PDF_PATH, conteudo)
    return SAMPLE_PDF_PATH


# =====================================================================
# Exemplo 1: Custo de tokens de imagem (cálculo local, sem API)
# =====================================================================

def exemplo_01_custo_tokens():
    print_header("EXEMPLO 1: Custo de tokens de imagem (cálculo local)")

    print("""
Fórmula: tokens = ceil(largura / 28) * ceil(altura / 28)
Cada patch de 28x28 pixels da imagem custa 1 token visual.
""")

    casos = [
        ("Ícone pequeno", 128, 128),
        ("Screenshot padrão", 1280, 720),
        ("Imagem do exemplo da doc (1000x1000)", 1000, 1000),
        ("Foto em alta resolução", 3024, 4032),
    ]

    print(f"{'Cenário':35} {'Dimensões':15} {'Tokens visuais':>15}")
    print("-" * 68)
    for nome, w, h in casos:
        tokens = calcular_tokens_imagem(w, h)
        print(f"{nome:35} {f'{w}x{h}':15} {tokens:>15,}")

    print("\n--- Agora com uma imagem real gerada para o exemplo ---")
    try:
        caminho = garantir_imagem_exemplo()
        largura, altura = get_image_dimensions(caminho)
        tokens = calcular_tokens_imagem(largura, altura)
        print(f"Arquivo: {caminho}")
        print(f"Dimensões reais: {largura}x{altura}")
        print(f"Custo estimado: {tokens:,} tokens visuais")
    except Exception as e:
        print(f"Não foi possível gerar/ler a imagem de exemplo: {e}")

    print("""
Conclusão prática (da documentação):
- 10 screenshots em alta resolução podem consumir tanto contexto
  quanto um system prompt detalhado.
- Se o pipeline estourar o orçamento de tokens, muitas vezes a
  correção é um simples passo de resize da imagem ANTES do envio.
- Os limites de resolução/token mudam entre modelos: sempre
  confira a página de Vision da documentação oficial no momento
  de construir o pipeline.
""")


# =====================================================================
# Exemplo 2: Envio de imagem via Base64 inline
# =====================================================================

def exemplo_02_base64():
    print_header("EXEMPLO 2: Envio de imagem via Base64 inline")

    caminho = garantir_imagem_exemplo()
    print(f"Usando imagem local: {caminho}")

    with open(caminho, "rb") as f:
        image_bytes = f.read()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    print(f"Tamanho do payload em base64: {len(image_b64):,} caracteres")
    print("Enviando para a API (chamada síncrona real)...\n")

    client = get_client()
    if client is None:
        return

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": "Descreva esta imagem em uma frase, em português."},
                ],
            }
        ],
    )

    print("Resposta do Claude:")
    for block in response.content:
        if block.type == "text":
            print(block.text)

    print(f"\nUso de tokens -> entrada: {response.usage.input_tokens}, "
          f"saída: {response.usage.output_tokens}")
    print("""
Observação: repare que TODO o payload base64 viaja a cada
requisição. Se essa mesma imagem fosse usada em várias chamadas,
o custo de rede se repetiria a cada vez (compare com o Exemplo 4,
Files API).
""")


# =====================================================================
# Exemplo 3: Envio de imagem via URL
# =====================================================================

def exemplo_03_url():
    print_header("EXEMPLO 3: Envio de imagem via URL")

    print(f"URL usada: {URL_IMAGEM_EXEMPLO}")
    print("(Edite a constante URL_IMAGEM_EXEMPLO neste arquivo para usar outra imagem)")
    print("Enviando para a API (chamada síncrona real)...\n")

    client = get_client()
    if client is None:
        return

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "url", "url": URL_IMAGEM_EXEMPLO},
                    },
                    {"type": "text", "text": "Descreva esta imagem em uma frase, em português."},
                ],
            }
        ],
    )

    print("Resposta do Claude:")
    for block in response.content:
        if block.type == "text":
            print(block.text)

    print(f"\nUso de tokens -> entrada: {response.usage.input_tokens}, "
          f"saída: {response.usage.output_tokens}")
    print("""
Observação: o payload enviado por nós é minúsculo (só a URL),
mas o custo em tokens de contexto é o mesmo de qualquer outra
forma de envio -- o que muda é o tamanho da REQUISIÇÃO, não o
custo de tokens visuais processados pelo modelo.
""")


# =====================================================================
# Exemplo 4: Envio via Files API (upload único + reuso)
# =====================================================================

def exemplo_04_files_api():
    print_header("EXEMPLO 4: Envio via Files API (upload único + reuso)")

    client = get_client()
    if client is None:
        return

    caminho = garantir_imagem_exemplo()
    print(f"Fazendo upload único do arquivo: {caminho}")

    try:
        with open(caminho, "rb") as f:
            upload = client.beta.files.upload(file=(caminho, f, "image/jpeg"))
    except Exception as e:
        print(f"Falha ao usar Files API (pode exigir header beta ou não estar "
              f"disponível na sua conta/plataforma): {e}")
        return

    file_id = upload.id
    print(f"Upload concluído. file_id = {file_id}")
    print("\nAgora reutilizamos o MESMO file_id em duas requisições diferentes, "
          "sem reenviar os bytes da imagem:\n")

    perguntas = [
        "Em uma frase, o que aparece nesta imagem?",
        "Quais são as cores predominantes desta imagem?",
    ]

    for i, pergunta in enumerate(perguntas, start=1):
        print(f"--- Requisição {i}: '{pergunta}' ---")
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=200,
            betas=["files-api-2025-04-14"],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "file", "file_id": file_id}},
                        {"type": "text", "text": pergunta},
                    ],
                }
            ],
        )
        for block in response.content:
            if block.type == "text":
                print(block.text)
        print()

    print("""
Observação: a partir do upload, cada nova requisição carregou
apenas o file_id (poucos bytes), em vez da imagem inteira em
base64. Isso é o que a documentação chama de "overhead cai para
quase zero" após o custo único de upload.
""")


# =====================================================================
# Exemplo 5: Envio de PDF (bloco "document")
# =====================================================================

def exemplo_05_pdf():
    print_header("EXEMPLO 5: Envio de PDF via bloco 'document'")

    caminho = garantir_pdf_exemplo()
    print(f"Usando PDF local: {caminho}")

    with open(caminho, "rb") as f:
        pdf_bytes = f.read()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    client = get_client()
    if client is None:
        return

    print("Enviando para a API (chamada síncrona real)...\n")
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                        "title": "documento_exemplo.pdf",
                    },
                    {
                        "type": "text",
                        "text": "Resuma o conteúdo deste PDF em até duas frases, em português.",
                    },
                ],
            }
        ],
    )

    print("Resposta do Claude:")
    for block in response.content:
        if block.type == "text":
            print(block.text)

    print(f"\nUso de tokens -> entrada: {response.usage.input_tokens}, "
          f"saída: {response.usage.output_tokens}")
    print("""
Observação: repare que a estrutura do 'source' é idêntica à usada
para imagens (base64 / url / file_id). A diferença está apenas no
'type' do bloco, que aqui é 'document', e nos campos opcionais
'title' e 'context'.
""")


# =====================================================================
# Exemplo 6: Prompting multimodal (ambiguidade visual)
# =====================================================================

def _perguntar_com_imagem(client, image_b64, prompt_texto):
    response = client.messages.create(
        model=MODEL,
        max_tokens=350,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt_texto},
                ],
            }
        ],
    )
    return "\n".join(b.text for b in response.content if b.type == "text")


def exemplo_06_prompting_multimodal():
    print_header("EXEMPLO 6: Prompting multimodal (prompt vago x prompt estruturado)")

    caminho = garantir_imagem_exemplo()
    with open(caminho, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    client = get_client()
    if client is None:
        return

    prompt_vago = "Descreva esta imagem."
    prompt_estruturado = (
        "Descreva esta imagem seguindo estas regras:\n"
        "1. Liste cada elemento visual separadamente.\n"
        "2. Se objetos estiverem sobrepostos, descreva cada um "
        "individualmente e indique a sobreposição.\n"
        "3. Indique relações de profundidade (o que está em primeiro "
        "plano e o que está ao fundo).\n"
        "4. Se algum elemento estiver parcialmente oculto/cortado, "
        "mencione isso explicitamente.\n"
        "Responda em português, em formato de lista."
    )

    print("--- Prompt vago (sem estrutura) ---")
    print(f"Prompt: {prompt_vago}\n")
    print(_perguntar_com_imagem(client, image_b64, prompt_vago))

    print("\n--- Prompt estruturado (trata ambiguidade explicitamente) ---")
    print(f"Prompt: {prompt_estruturado}\n")
    print(_perguntar_com_imagem(client, image_b64, prompt_estruturado))

    print("""
Conclusão (da documentação):
- Um prompt vazio tipo "descreva esta imagem" produz saída rasa,
  pelo mesmo motivo que um prompt de texto vazio produz: falta um
  alvo estrutural.
- Imagens carregam ambiguidades que texto não carrega (objetos
  sobrepostos, profundidade, oclusão parcial). Um bom prompt
  visual nomeia explicitamente como tratar cada tipo de
  ambiguidade.
""")


# =====================================================================
# Exemplo 7: Message Batches API
# =====================================================================

def exemplo_07_batches():
    print_header("EXEMPLO 7: Message Batches API (processamento assíncrono em lote)")

    client = get_client()
    if client is None:
        return

    itens = [
        {"custom_id": "cliente-1", "texto": "Produto chegou quebrado, quero reembolso."},
        {"custom_id": "cliente-2", "texto": "Adorei o produto, chegou antes do prazo!"},
        {"custom_id": "cliente-3", "texto": "Ainda não recebi, já se passaram 20 dias."},
    ]

    requests_batch = []
    for item in itens:
        requests_batch.append({
            "custom_id": item["custom_id"],
            "params": {
                "model": MODEL,
                "max_tokens": 50,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Classifique o sentimento deste comentário de cliente "
                            "como POSITIVO, NEGATIVO ou NEUTRO. Responda só com a "
                            f"palavra da classificação.\n\nComentário: {item['texto']}"
                        ),
                    }
                ],
            },
        })

    print(f"Submetendo lote com {len(requests_batch)} requisições...")
    batch = client.messages.batches.create(requests=requests_batch)
    print(f"batch_id = {batch.id}")
    print(f"Status inicial: {batch.processing_status}")

    print("\nFazendo polling do status (isso pode levar alguns segundos a minutos)...")
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        print(f"  status atual: {batch.processing_status}")
        if batch.processing_status == "ended":
            break
        time.sleep(5)

    print("\nLote concluído. Baixando resultados:\n")
    for resultado in client.messages.batches.results(batch.id):
        custom_id = resultado.custom_id
        if resultado.result.type == "succeeded":
            msg = resultado.result.message
            texto_resposta = "".join(b.text for b in msg.content if b.type == "text")
            print(f"[{custom_id}] -> {texto_resposta.strip()}")
        else:
            print(f"[{custom_id}] -> falhou: {resultado.result.type}")

    print("""
Observação:
- Cada requisição do lote tem um 'custom_id' próprio, usado para
  casar a resposta com a requisição original ao final.
- O custo por token no Batch API é menor que no modo síncrono,
  mas em troca você não tem resposta imediata.
- Este é o padrão certo para pipelines noturnos, avaliações em
  massa, e classificação de grandes volumes de dados -- nunca
  para um chatbot respondendo um usuário em tempo real.
""")


# =====================================================================
# Exemplo 8: Combinando multimodal + batch (e erros comuns)
# =====================================================================

def _parte_a_pipeline_offline(client):
    print("\n--- Parte A: pipeline offline (Files API + Batches API) ---")

    caminho = garantir_imagem_exemplo()
    print(f"1) Upload único via Files API: {caminho}")
    with open(caminho, "rb") as f:
        upload = client.beta.files.upload(file=(caminho, f, "image/jpeg"))
    file_id = upload.id
    print(f"   file_id = {file_id}")

    print("2) Montando lote reaproveitando o mesmo file_id em 3 'perguntas de "
          "classificação' diferentes, simulando um pipeline noturno:")

    perguntas = [
        "Esta imagem contém uma flor? Responda SIM ou NAO.",
        "A imagem é predominantemente colorida ou em tons neutros? Responda "
        "COLORIDA ou NEUTRA.",
        "A imagem parece ter sido tirada ao ar livre ou em ambiente interno? "
        "Responda AR_LIVRE ou INTERNO.",
    ]

    requests_batch = []
    for i, pergunta in enumerate(perguntas, start=1):
        requests_batch.append({
            "custom_id": f"img-check-{i}",
            "params": {
                "model": MODEL,
                "max_tokens": 20,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "file", "file_id": file_id}},
                            {"type": "text", "text": pergunta},
                        ],
                    }
                ],
            },
        })

    batch = client.messages.batches.create(requests=requests_batch)
    print(f"   batch_id = {batch.id} (status inicial: {batch.processing_status})")

    print("3) Polling...")
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        print(f"   status atual: {batch.processing_status}")
        if batch.processing_status == "ended":
            break
        time.sleep(5)

    print("4) Resultados do lote:")
    for resultado in client.messages.batches.results(batch.id):
        if resultado.result.type == "succeeded":
            msg = resultado.result.message
            texto = "".join(b.text for b in msg.content if b.type == "text")
            print(f"   [{resultado.custom_id}] -> {texto.strip()}")
        else:
            print(f"   [{resultado.custom_id}] -> falhou: {resultado.result.type}")

    print("""
   Por que isso funciona: o file_id evita reenviar os bytes da
   imagem em cada uma das 3 requisições, e o Batches API absorve
   a latência de um job que não precisa de resposta imediata.
""")


def _parte_b_erros_comuns():
    print("\n--- Parte B: os dois erros comuns (simulação, sem chamada de API) ---")

    print("""
ERRO 1: usar batch onde deveria ser síncrono
  Cenário: "usuário sobe uma foto e espera classificação imediata"
  Se você mandar isso para o Batches API, o usuário pode esperar
  minutos ou até horas por uma resposta que deveria levar
  segundos. O pipeline passa nos testes (a resposta eventualmente
  chega) mas falha em produção (o usuário já foi embora).
  -> Regra: fluxo com usuário esperando na tela = API síncrona.
""")

    print("ERRO 2: subestimar custo de contexto com múltiplas imagens grandes")
    caminho = garantir_imagem_exemplo()
    largura, altura = get_image_dimensions(caminho)
    tokens_por_imagem = calcular_tokens_imagem(largura, altura)

    for n_imagens in [1, 5, 20, 50]:
        total_tokens = tokens_por_imagem * n_imagens
        print(f"  {n_imagens:>3} imagens de {largura}x{altura} por requisição "
              f"-> {total_tokens:,} tokens visuais só de imagem")

    print("""
  Se um pipeline carrega várias imagens grandes por requisição
  (por exemplo, 50 fotos de um mesmo relatório), o custo de
  contexto pode estourar o limite do modelo ANTES de processar
  qualquer texto do prompt.
  -> Regra: meça o custo de tokens em inputs de escala real de
     produção antes de construir o pipeline, não depois.
""")


def exemplo_08_multimodal_batch():
    print_header("EXEMPLO 8: Combinando multimodal + batch, e erros comuns a evitar")

    client = get_client()
    if client is not None:
        try:
            _parte_a_pipeline_offline(client)
        except Exception as e:
            print(f"Não foi possível rodar a Parte A (Files API + Batches API): {e}")

    _parte_b_erros_comuns()


# =====================================================================
# Menu principal
# =====================================================================

MENU = {
    "1": ("Custo de tokens de imagem (cálculo local, sem API)", exemplo_01_custo_tokens),
    "2": ("Envio de imagem via Base64 inline", exemplo_02_base64),
    "3": ("Envio de imagem via URL", exemplo_03_url),
    "4": ("Envio via Files API (upload único + reuso)", exemplo_04_files_api),
    "5": ("Envio de PDF (bloco 'document')", exemplo_05_pdf),
    "6": ("Prompting multimodal (tratando ambiguidade visual)", exemplo_06_prompting_multimodal),
    "7": ("Message Batches API (processamento em lote)", exemplo_07_batches),
    "8": ("Combinando multimodal + batch (e erros comuns)", exemplo_08_multimodal_batch),
}


def exibir_menu():
    print("\n" + "#" * 70)
    print("# Claude Docs — Imagens, PDFs e Processamento em Alto Volume")
    print("#" * 70)

    status_key = "OK" if os.environ.get("ANTHROPIC_API_KEY") else "NÃO CONFIGURADA"
    print(f"ANTHROPIC_API_KEY: {status_key}\n")

    for chave, (descricao, _) in MENU.items():
        print(f"  [{chave}] {descricao}")
    print("  [0] Sair")


def main():
    while True:
        exibir_menu()
        escolha = input("\nEscolha uma opção: ").strip()

        if escolha == "0":
            print("Encerrando. Até mais!")
            sys.exit(0)

        opcao = MENU.get(escolha)
        if opcao is None:
            print("Opção inválida, tente novamente.")
            continue

        _, funcao = opcao
        try:
            funcao()
        except Exception as e:
            print(f"\n[ERRO ao executar o exemplo] {e}")

        input("\nPressione ENTER para voltar ao menu...")


if __name__ == "__main__":
    main()