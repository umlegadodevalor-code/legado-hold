# Legado Hold v3.3 — Deploy limpo

Esta versão foi feita para **um único Web Service no Render**.

## Estrutura correta no GitHub

A raiz do repositório deve conter SOMENTE:

- `app.py`
- `requirements.txt`
- `render.yaml`
- `README.md`
- pasta `static/`
  - `index.html`

Não envie ZIP para o GitHub.
Não deixe versões antigas `legado-hold-v3_1.html`, `v3_2.html` etc. no repositório.

## Render

Crie/edite um **Web Service**, não um Static Site.

Build:
`pip install -r requirements.txt`

Start:
`gunicorn app:app`

Variáveis de ambiente no Render:
- `BRAPI_TOKEN`
- `TWELVEDATA_TOKEN`

Esses tokens ficam SOMENTE no painel do Render. O aluno nunca vê nem informa token.

## Como a aplicação funciona

O navegador acessa:
`https://SEU-SITE.onrender.com`

A própria página chama:
- `/api/quotes`
- `/api/benchmarks`
- `/api/tesouro`

Como frontend e backend usam o MESMO domínio, não há campo de backend no site e não há dependência de `localhost`.

## Teste após deploy

Abra:
`https://SEU-SITE.onrender.com/api/health`

Deve retornar JSON com:
- `"ok": true`
- `"frontend_mode": "same-origin"`
- `"brapi_configured": true` (se o token foi configurado)
- `"twelvedata_configured": true` (se o token foi configurado)

Depois abra a página principal e pressione Ctrl+F5.
