import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

MAX_TOKENS = 4096

client = anthropic.Anthropic(api_key=API_KEY)

def use_streaming_response(system_prompt, history):
    resposta = ""

    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=history
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                resposta += event.delta.text
                print(event.delta.text, end="", flush=True)

        response = stream.get_final_message()

    return response, resposta

def main():
    system_prompt = input("Digite o prompt do sistema: ")
    print()

    history = []
    while True:
        user_prompt = input("Voce: ").strip()

        if user_prompt.lower() == "sair":
            break

        if not user_prompt:
            print("Nenhuma pergunta informada. Tente novamente.\n")
            continue

        history.append({"role": "user", "content": user_prompt})

        print("\nClaude: ", end="", flush=True)

        response, content = use_streaming_response(system_prompt, history)

        if response.stop_reason == "end_turn":
            history.append({"role": "assistant", "content": content})

        print()

if __name__ == "__main__":
    main()
