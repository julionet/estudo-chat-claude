from deep_translator import GoogleTranslator


def main():
    tradutor = GoogleTranslator(source="pt", target="en")

    print("=== Tradutor Português → Inglês ===")
    print("Digite 'sair' para encerrar.\n")

    while True:
        texto = input("Texto (PT): ").strip()
        if texto.lower() == "sair":
            break
        if not texto:
            continue
        traducao = tradutor.translate(texto)
        print(f"Tradução (EN): {traducao}\n")


if __name__ == "__main__":
    main()
