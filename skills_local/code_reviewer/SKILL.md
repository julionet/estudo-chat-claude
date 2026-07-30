---
name: python-code-reviewer
description: Use this skill whenever the user pastes Python code and asks for a review, code review, feedback, bugs, or improvements. Trigger on words like "revisar codigo", "code review", "revise esse python", "bugs no meu codigo".
---
 
# Python Code Reviewer Skill
 
Ao revisar codigo Python, siga sempre esta checklist e responda em formato de lista:
 
1. **Corretude**: existe algum bug logico ou excecao nao tratada?
2. **Legibilidade**: nomes de variaveis, funcoes muito longas, complexidade.
3. **Performance**: loops ou estruturas de dados ineficientes.
4. **Boas praticas**: uso de type hints, docstrings, PEP8.
5. **Seguranca**: uso de eval/exec, input nao sanitizado, segredos hardcoded.
Termine sempre com uma nota de 0 a 10 e o principal ponto a melhorar.