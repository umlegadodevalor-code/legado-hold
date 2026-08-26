import os
import csv
import io
import time
import unicodedata
from datetime import datetime, timezone
from threading import Lock
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder=None)

BRAPI_TOKEN = os.getenv("BRAPI_TOKEN", "").strip()
TWELVEDATA_TOKEN = os.getenv("TWELVEDATA_TOKEN", "").strip()

TESOURO_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/"
    "precotaxatesourodireto.csv"
)

_session = requests.Session()
_session.headers.update({"User-Agent": "LegadoHold/1.0 (+personal-finance-dashboard)"})

_tesouro_cache = {"loaded_at": 0.0, "rows": [], "source_updated": None}
_tesouro_lock = Lock()
TESOURO_CACHE_SECONDS = 12 * 60 * 60

_quote_cache = {}
QUOTE_CACHE_SECONDS = 5 * 60

_rate = {}
RATE_WINDOW_SECONDS = 10 * 60
RATE_MAX_REQUESTS = 180

def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.remote_addr) or "unknown"

def _rate_allowed():
    now = time.time()
    ip = _client_ip()
    bucket = _rate.setdefault(ip, [])
    bucket[:] = [t for t in bucket if now - t < RATE_WINDOW_SECONDS]
    if len(bucket) >= RATE_MAX_REQUESTS:
        return False
    bucket.append(now)
    return True

def _cache_get(key):
    item = _quote_cache.get(key)
    if not item:
        return None
    if time.time() - item["at"] > QUOTE_CACHE_SECONDS:
        _quote_cache.pop(key, None)
        return None
    return item["value"]

def _cache_set(key, value):
    if value is not None:
        _quote_cache[key] = {"at": time.time(), "value": value}
    return value

def _norm_text(value):
    s = unicodedata.normalize("NFD", str(value or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().strip().split())

def _parse_date(value):
    s = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return ""

def _num_br(value):
    s = str(value or "").strip().replace("%", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

def _family_matches(csv_name, family):
    csvn = _norm_text(csv_name)
    fam = _norm_text(family)
    aliases = {
        "tesouro selic": ["tesouro selic", "lft"],
        "tesouro prefixado": ["tesouro prefixado", "ltn"],
        "tesouro prefixado com juros semestrais": [
            "tesouro prefixado com juros semestrais", "ntn-f", "ntnf"
        ],
        "tesouro ipca+": ["tesouro ipca+", "ntn-b principal", "ntnb principal"],
        "tesouro ipca+ com juros semestrais": [
            "tesouro ipca+ com juros semestrais", "ntn-b", "ntnb"
        ],
        "tesouro renda+": ["tesouro renda+", "renda+"],
        "tesouro educa+": ["tesouro educa+", "educa+"],
    }
    return any(a == csvn or a in csvn for a in aliases.get(fam, [fam]))

def _download_tesouro_rows(force=False):
    now = time.time()
    with _tesouro_lock:
        if (
            not force
            and _tesouro_cache["rows"]
            and now - _tesouro_cache["loaded_at"] < TESOURO_CACHE_SECONDS
        ):
            return _tesouro_cache["rows"]

        try:
            r = _session.get(TESOURO_CSV_URL, timeout=40)
            r.raise_for_status()
        except requests.RequestException:
            # Fallback: descobre a URL atual via CKAN se o recurso mudar.
            meta = _session.get(
                "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show",
                params={"id": "taxas-dos-titulos-ofertados-pelo-tesouro-direto"},
                timeout=20,
            )
            meta.raise_for_status()
            resources = (meta.json().get("result") or {}).get("resources") or []
            csv_res = next((x for x in resources if str(x.get("format","")).upper()=="CSV"), None)
            if not csv_res or not csv_res.get("url"):
                raise RuntimeError("recurso CSV do Tesouro não encontrado no CKAN")
            r = _session.get(csv_res["url"], timeout=40)
            r.raise_for_status()

        content = r.content
        text = None
        for enc in ("utf-8-sig", "cp1252", "latin1"):
            try:
                text = content.decode(enc)
                if "Tipo T" in text[:1000] or "tipo t" in text[:1000].lower():
                    break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = content.decode("latin1", errors="replace")

        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        rows = []

        def pick(row, *names):
            normalized = {_norm_text(k): v for k, v in row.items()}
            for name in names:
                key = _norm_text(name)
                if key in normalized:
                    return normalized[key]
            return ""

        for row in reader:
            tipo = pick(row, "Tipo Titulo", "Tipo Título")
            venc = _parse_date(pick(row, "Data Vencimento"))
            data_base = _parse_date(pick(row, "Data Base"))
            if not tipo or not venc or not data_base:
                continue
            rows.append({
                "tipo": tipo,
                "vencimento": venc,
                "data_base": data_base,
                "pu_base": _num_br(pick(row, "PU Base Manha", "PU Base Manhã")),
                "pu_venda": _num_br(pick(row, "PU Venda Manha", "PU Venda Manhã")),
                "pu_compra": _num_br(pick(row, "PU Compra Manha", "PU Compra Manhã")),
                "taxa_venda": _num_br(pick(row, "Taxa Venda Manha", "Taxa Venda Manhã")),
                "taxa_compra": _num_br(pick(row, "Taxa Compra Manha", "Taxa Compra Manhã")),
            })

        _tesouro_cache.update(
            loaded_at=now,
            rows=rows,
            source_updated=max((x["data_base"] for x in rows), default=None),
        )
        return rows

def get_tesouro(family, maturity):
    cache_key = ("tesouro", _norm_text(family), _parse_date(maturity))
    cached = _cache_get(cache_key)
    if cached:
        return cached
    rows = _download_tesouro_rows()
    maturity = _parse_date(maturity)
    candidates = [
        r for r in rows
        if _family_matches(r["tipo"], family)
        and r["vencimento"] == maturity
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["data_base"], reverse=True)
    row = candidates[0]
    price = row["pu_base"] or row["pu_venda"] or row["pu_compra"]
    if not price:
        return None
    return _cache_set(cache_key, {
        "currency": "BRL",
        "price": price,
        "rate": row["taxa_venda"] if row["taxa_venda"] is not None else row["taxa_compra"],
        "buy_rate": row["taxa_compra"],
        "sell_rate": row["taxa_venda"],
        "base_date": row["data_base"],
        "maturity": row["vencimento"],
        "official_name": row["tipo"],
        "price_field": (
            "PU Base Manhã" if row["pu_base"]
            else "PU Venda Manhã" if row["pu_venda"]
            else "PU Compra Manhã"
        ),
        "source": "Tesouro Transparente",
    })

def get_brapi(symbol):
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        return None
    cached = _cache_get(("b3", symbol))
    if cached:
        return cached
    headers = {}
    if BRAPI_TOKEN:
        headers["Authorization"] = f"Bearer {BRAPI_TOKEN}"
    url = f"https://brapi.dev/api/quote/{requests.utils.quote(symbol)}"
    r = _session.get(url, headers=headers, timeout=15)
    if not r.ok:
        return None
    data = r.json()
    item = (data.get("results") or [None])[0]
    if not item:
        return None
    price = item.get("regularMarketPrice")
    if price is None:
        return None
    return _cache_set(("b3", symbol), {
        "currency": "BRL",
        "price": float(price),
        "source": "Brapi",
    })

def get_usdbrl():
    cached = _cache_get(("fx", "USD-BRL"))
    if cached:
        return cached

    if TWELVEDATA_TOKEN:
        url = "https://api.twelvedata.com/price"
        r = _session.get(url, params={"symbol": "USD/BRL", "apikey": TWELVEDATA_TOKEN}, timeout=15)
        if r.ok:
            try:
                p = float(r.json().get("price"))
                if p > 0:
                    return _cache_set(("fx", "USD-BRL"), p)
            except Exception:
                pass

    if BRAPI_TOKEN:
        try:
            headers = {"Authorization": f"Bearer {BRAPI_TOKEN}"}
            r = _session.get(
                "https://brapi.dev/api/v2/currency",
                params={"currency": "USD-BRL"},
                headers=headers,
                timeout=15,
            )
            if r.ok:
                data = r.json()
                candidates = (
                    data.get("currency")
                    or data.get("currencies")
                    or data.get("results")
                    or []
                )
                if isinstance(candidates, dict):
                    candidates = [candidates]
                if candidates:
                    item = candidates[0]
                    p = item.get("bidPrice") or item.get("bid") or item.get("price")
                    p = float(p)
                    if p > 0:
                        return _cache_set(("fx", "USD-BRL"), p)
        except Exception:
            pass
    return None

def get_twelve(symbol):
    symbol = str(symbol or "").strip().upper()
    if not symbol or not TWELVEDATA_TOKEN:
        return None
    cached = _cache_get(("eua", symbol))
    if cached:
        return cached
    r = _session.get(
        "https://api.twelvedata.com/price",
        params={"symbol": symbol, "apikey": TWELVEDATA_TOKEN},
        timeout=15,
    )
    if not r.ok:
        return None
    try:
        price = float(r.json().get("price"))
    except Exception:
        return None
    if price <= 0:
        return None
    return _cache_set(("eua", symbol), {"currency": "USD", "price": price, "source": "Twelve Data"})

CRYPTO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
}

def normalize_crypto(symbol):
    s = str(symbol or "").strip().upper()
    aliases = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL", "CARDANO": "ADA"}
    return aliases.get(s, s.replace("/BRL", "").replace("-BRL", ""))

def get_crypto(symbol):
    sym = normalize_crypto(symbol)
    cached = _cache_get(("crypto", sym))
    if cached:
        return cached

    # Binance direct BRL
    try:
        r = _session.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": f"{sym}BRL"},
            timeout=10,
        )
        if r.ok:
            p = float(r.json()["price"])
            if p > 0:
                return _cache_set(("crypto", sym), {"currency": "BRL", "price": p, "source": "Binance"})
    except Exception:
        pass

    # CoinGecko public fallback
    cg_id = CRYPTO_IDS.get(sym)
    if cg_id:
        try:
            r = _session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": cg_id, "vs_currencies": "brl"},
                timeout=10,
            )
            if r.ok:
                p = float(r.json()[cg_id]["brl"])
                if p > 0:
                    return _cache_set(("crypto", sym), {"currency": "BRL", "price": p, "source": "CoinGecko"})
        except Exception:
            pass
    return None

@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "service": "Legado Hold backend",
        "tesouro_cache_date": _tesouro_cache.get("source_updated"),
        "brapi_configured": bool(BRAPI_TOKEN),
        "twelvedata_configured": bool(TWELVEDATA_TOKEN),
        "frontend_mode": "same-origin",
    })

@app.get("/api/tesouro")
def api_tesouro():
    family = request.args.get("familia", "").strip()
    maturity = request.args.get("vencimento", "").strip()
    if not family or not maturity:
        return jsonify({"ok": False, "error": "familia e vencimento são obrigatórios"}), 400
    try:
        q = get_tesouro(family, maturity)
    except Exception as e:
        return jsonify({"ok": False, "error": f"falha ao ler Tesouro: {e}"}), 502
    if not q:
        return jsonify({"ok": False, "error": "título/vencimento não encontrado"}), 404
    return jsonify({"ok": True, **q})

@app.post("/api/quotes")
def api_quotes():
    if not _rate_allowed():
        return jsonify({"ok": False, "error": "limite temporário de requisições"}), 429
    payload = request.get_json(silent=True) or {}
    assets = payload.get("assets") or []
    if not isinstance(assets, list):
        return jsonify({"ok": False, "error": "assets deve ser uma lista"}), 400
    if len(assets) > 100:
        return jsonify({"ok": False, "error": "máximo de 100 ativos por requisição"}), 400
    usdbrl = get_usdbrl()
    results = []

    for asset in assets:
        typ = str(asset.get("type") or "").lower()
        symbol = str(asset.get("symbol") or "").strip().upper()
        key = asset.get("key") or symbol
        try:
            quote = None
            if typ == "tesouro":
                quote = get_tesouro(asset.get("family", ""), asset.get("maturity", ""))
            elif typ == "eua":
                quote = get_twelve(symbol)
            elif typ == "cripto":
                quote = get_crypto(symbol)
            elif typ == "b3":
                quote = get_brapi(symbol)
            elif typ == "manual":
                quote = None

            if quote:
                item = {"key": key, "symbol": symbol, "ok": True, **quote}
                if quote.get("currency") == "USD" and usdbrl:
                    item["usdbrl"] = usdbrl
                    item["price_brl"] = quote["price"] * usdbrl
                results.append(item)
            else:
                results.append({"key": key, "symbol": symbol, "ok": False, "error": "cotação indisponível"})
        except Exception as e:
            results.append({"key": key, "symbol": symbol, "ok": False, "error": str(e)})

    return jsonify({
        "ok": True,
        "usdbrl": usdbrl,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    })


@app.get("/api/benchmarks")
def api_benchmarks():
    if not _rate_allowed():
        return jsonify({"ok": False, "error": "limite temporário de requisições"}), 429
    try:
        cdi_r = _session.get(
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados/ultimos/1",
            params={"formato": "json"},
            timeout=15,
        )
        ipca_r = _session.get(
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1",
            params={"formato": "json"},
            timeout=15,
        )
        cdi_r.raise_for_status()
        ipca_r.raise_for_status()
        cdi_data, ipca_data = cdi_r.json(), ipca_r.json()
        cdi_daily = float(str(cdi_data[0]["valor"]).replace(",", "."))
        cdi_aa = ((1 + cdi_daily/100) ** 252 - 1) * 100
        ipca_12m = float(str(ipca_data[0]["valor"]).replace(",", "."))
        return jsonify({
            "ok": True,
            "cdi_aa": cdi_aa,
            "ipca_12m": ipca_12m,
            "source": "Banco Central do Brasil",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"falha ao consultar BCB: {e}"}), 502

@app.post("/api/tesouro/cache/refresh")
def refresh_tesouro_cache():
    # In a public prototype this endpoint is harmless: it only refreshes public data.
    try:
        rows = _download_tesouro_rows(force=True)
        return jsonify({"ok": True, "rows": len(rows), "base_date": _tesouro_cache["source_updated"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

@app.get("/")
def index():
    return send_from_directory(Path(__file__).parent, "index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
