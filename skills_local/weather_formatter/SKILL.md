---
name: weather-formatter
description: Use this skill whenever the user asks to format, summarize, or present weather data (temperature, forecast, humidity, wind) in a clean human-readable report. Trigger on words like "clima", "previsao do tempo", "temperatura", "forecast".
---
 
# Weather Formatter Skill
 
Quando receber dados de clima (mesmo que informais, tipo "28 graus, vento 10km/h, 60% de chance de chuva"),
formate a resposta SEMPRE neste padrao:
 
    🌡️  Temperatura: <valor>
    💨  Vento: <valor>
    🌧️  Chance de chuva: <valor>
    📝  Recomendacao: <uma frase curta e pratica>
 
Nunca invente dados que o usuario nao forneceu. Se faltar algum dado, escreva "nao informado" no campo.
 