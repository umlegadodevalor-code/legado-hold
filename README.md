# Legado Hold v3.4 — Deploy simplificado

## Coloque SOMENTE estes 5 arquivos na raiz do repositório GitHub

- `app.py`
- `index.html`
- `requirements.txt`
- `render.yaml`
- `README.md`

Não envie ZIP.
Não crie pasta `static`.
Não envie versões antigas do Legado Hold.

## Render

Crie um **Web Service**.

Build Command:
`pip install -r requirements.txt`

Start Command:
`gunicorn app:app`

Em **Environment Variables**, cadastre:
- `BRAPI_TOKEN`
- `TWELVEDATA_TOKEN`

Os tokens ficam somente no Render. Eles não aparecem no site.

## Testes depois do deploy

1. Abra:
   `https://SEU-SITE.onrender.com/api/health`

2. Deve aparecer JSON com `"ok": true`.

3. Depois abra:
   `https://SEU-SITE.onrender.com/`

   A interface do Legado Hold deve aparecer.

4. Pressione `Ctrl + F5` se o navegador estiver exibindo uma versão antiga.

## Estrutura correta

```
/
├── app.py
├── index.html
├── README.md
├── render.yaml
└── requirements.txt
```
