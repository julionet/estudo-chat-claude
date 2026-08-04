from transformers import AutoTokenizer

sentence = "Hello, how are you?"

# Load a pre-trained tokenizer
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

input_ids = tokenizer(sentence).input_ids

print("Input IDs:", input_ids)

for id in input_ids:
    print(tokenizer.decode(id))

colors = [
    '102;194;165', '252;141;98', '141;160;203',
    '231;138;195', '166;216;84', '255;217;47'
]

def show_tokens(sentence: str, tokenizer_name: str):
    """ Show the tokens each separated by a different color """

    # Load the tokenizer and tokenize the input
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    token_ids = tokenizer(sentence).input_ids

    # Extract vocabulary length
    print(f"Vocab length: {len(tokenizer)}")

    # Print a colored list of tokens
    for idx, t in enumerate(token_ids):
        print(
            f'\x1b[0;30;48;2;{colors[idx % len(colors)]}m' +
            tokenizer.decode(t) +
            '\x1b[0m',
            end=' '
        )

text = """
English and CAPITALIZATION
🎵 鸟
show_tokens False None elif == >= else: two tabs:"    " Three tabs: "       "
12.0*50=600
"""

show_tokens(text, "bert-base-uncased")

print()

show_tokens(text, "Xenova/gpt-4")

show_tokens(text, "gpt2")

show_tokens(text, "google/flan-t5-small")

show_tokens(text, "bigcode/starcoder2-15b")

show_tokens(text, "microsoft/Phi-3-mini-4k-instruct")

show_tokens(text, "Qwen/Qwen2-VL-7B-Instruct")