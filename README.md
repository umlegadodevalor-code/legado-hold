# Legado Hold — Backend de Cotações

Este backend resolve o problema do `file://`/CORS e centraliza as fontes de dados.

## Fontes

- Tesouro Direto: CSV oficial do Tesouro Transparente, com cache em memória por 12 horas.
- Ações/FIIs B3: Brapi (`BRAPI_TOKEN` no servidor).
- Stocks/REITs/ETFs EUA: Twelve Data (`TWELVEDATA_TOKEN` no servidor).
- USD/BRL: Twelve Data, com fallback pela Brapi.
- Bitcoin/cripto: Binance pública, com fallback CoinGecko.

Nenhum token precisa ficar dentro do HTML.

## Testar localmente

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt

# Windows PowerShell:
$env:BRAPI_TOKEN="SEU_TOKEN"
$env:TWELVEDATA_TOKEN="SEU_TOKEN"

python app.py
```

Teste no navegador:

`http://localhost:5000/api/health`

Exemplo Tesouro:

`http://localhost:5000/api/tesouro?familia=Tesouro%20IPCA%2B&vencimento=2032-05-15`

## Render

1. Coloque estes arquivos em um repositório GitHub.
2. No Render: **New > Web Service**.
3. Conecte o repositório.
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn app:app`
6. Cadastre as variáveis de ambiente:
   - `BRAPI_TOKEN`
   - `TWELVEDATA_TOKEN`
7. Após o deploy, você receberá algo como:
   `https://legado-hold-api.onrender.com`
8. Cole esse endereço no campo **URL do backend** no HTML do Legado Hold.

O `render.yaml` também pode ser usado para configurar o serviço.

## Cache do Tesouro

O CSV oficial tem cerca de 13,7 MB. O backend baixa o arquivo automaticamente e guarda os registros em memória por 12 horas. O usuário não precisa baixar ou enviar CSV.

Quando a instância reinicia ou o cache expira, o próximo pedido baixa a base novamente.

## API unificada

`POST /api/quotes`

Exemplo:

```json
{
  "assets": [
    {"key":"petr4","type":"b3","symbol":"PETR4"},
    {"key":"btc","type":"cripto","symbol":"BTC"},
    {"key":"aapl","type":"eua","symbol":"AAPL"},
    {
      "key":"ipca2032",
      "type":"tesouro",
      "symbol":"IPCA+2032",
      "family":"Tesouro IPCA+",
      "maturity":"2032-05-15"
    }
  ]
}
```
