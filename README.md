# Legado Hold v3.5 — Tema claro

Esta versão mantém o backend robusto da v3.4.4 e altera apenas a apresentação visual.

## Arquivos para o GitHub
- app.py
- index.html
- requirements.txt
- render.yaml
- README.md

## Render
Build Command:
`pip install -r requirements.txt`

Start Command:
`gunicorn app:app`

Variáveis de ambiente:
- `BRAPI_TOKEN`
- `TWELVEDATA_TOKEN`

## Alterações visuais
- Fundo claro e suave
- Cards brancos
- Azul como cor principal
- Verde/vermelho apenas para estados e resultados
- Cotações com menor peso visual
- Maior destaque para patrimônio, visão da carteira e sugestão de aporte
