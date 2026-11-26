import os
import time
import logging
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import numpy as np
import pandas as pd
import requests
import yfinance as yf

# Yahoo Finance gereksiz log/warning çıktılarını gizleme
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ==================== Mini Web Sunucusu (Render Keep-Alive) ====================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"BIST 100 1H Kelly & Monte Carlo Bot Calisiyor!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_web_server():
    port_raw = os.environ.get("PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError:
        port = 8080
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Web sunucusu {port} portunda baslatildi.", flush=True)
    server.serve_forever()

# ==================== Bot Ayarları ====================
TELEGRAM_TOKEN = "8853048772:AAEW22ekJlDBc3EK9pWTiC8plZVm_9RBwas"
CHAT_ID = "1131754179"

TIMEFRAME = "1h"
DATA_PERIOD = "60d"
SCAN_INTERVAL_SEC = 3600  # 1 saat

BIST_HISSELERI = [
    "AEFES.IS", "AGHOL.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKFGY.IS", "AKFYE.IS", "AKSA.IS", "AKSEN.IS", "ALARK.IS",
    "ALBRK.IS", "ALFAS.IS", "ANSGR.IS", "ARCLK.IS", "ARDYZ.IS", "ASELS.IS", "ASTOR.IS", "BERA.IS", "BIENY.IS", "BIMAS.IS",
    "BIOEN.IS", "BOBET.IS", "BRSAN.IS", "BRYAT.IS", "BUCIM.IS", "CANTE.IS", "CCOLA.IS", "CIMSA.IS", "CWENE.IS", "DOAS.IS",
    "DOHOL.IS", "ECILC.IS", "ECZYT.IS", "EGEEN.IS", "EKGYO.IS", "ENJSA.IS", "ENKAI.IS", "EREGL.IS", "EUPWR.IS", "FROTO.IS",
    "GARAN.IS", "GESAN.IS", "GUBRF.IS", "HALKB.IS", "HEKTS.IS", "ISCTR.IS", "ISGYO.IS", "ISMEN.IS", "IZENR.IS", "KAYSE.IS",
    "KCAER.IS", "KCHOL.IS", "KLSER.IS", "KONTR.IS", "KORDS.IS", "KRDMD.IS", "KSTUR.IS", "LMKDC.IS", "MAALT.IS", "MAVI.IS",
    "MHRGY.IS", "MIATK.IS", "MGROS.IS", "MPARK.IS", "ODAS.IS", "OTKAR.IS", "OYYAT.IS", "OYAKC.IS", "PASEU.IS", "PETKM.IS",
    "PGSUS.IS", "PLTUR.IS", "PSGYO.IS", "REEDR.IS", "SAHOL.IS", "SASA.IS", "SDTTR.IS", "SISE.IS", "SKBNK.IS", "SMRTG.IS",
    "SOKM.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS", "TKFEN.IS", "TMSN.IS", "TOASO.IS", "TSKB.IS", "TTKOM.IS", "TTRAK.IS",
    "TUKAS.IS", "TUPRS.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YEOTK.IS", "YKBNK.IS", "YYLGD.IS", "ZOREN.IS"
]

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram hatasi: {e}", flush=True)

# ==================== İndikatör Hesaplamaları ====================
def calculate_atr(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)

def calculate_adx(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean().replace(0, np.nan)
    plus_di = 100.0 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100.0 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx.fillna(0.0)

# ==================== Kelly Kriteri & Monte Carlo ====================
def calculate_kelly_fraction(returns_series, lookback=120):
    """
    Son 'lookback' barlık getirilerden:
    p = pozitif bar olasılığı
    b = ortalama kazanç / ortalama kayıp
    full_kelly = p - (1 - p) / b
    half_kelly = max(0.0, min(0.25, full_kelly * 0.5))  # Güvenli üst sınır %25
    """
    recent = returns_series.dropna().tail(lookback)
    if len(recent) < 20:
        return 0.0, 0.0, 0.0

    wins = recent[recent > 0]
    losses = recent[recent < 0].abs()

    if len(wins) == 0 or len(losses) == 0:
        return 0.0, 0.0, 0.0

    win_prob = float(len(wins) / len(recent))
    avg_win = float(wins.mean())
    avg_loss = float(losses.mean())
    if avg_loss <= 0:
        return 0.0, win_prob, 0.0

    payoff_ratio = avg_win / avg_loss
    full_kelly = win_prob - ((1.0 - win_prob) / payoff_ratio)
    half_kelly = max(0.0, min(0.25, full_kelly * 0.5))
    return round(half_kelly * 100, 2), round(win_prob * 100, 1), round(payoff_ratio, 2)

def run_monte_carlo(returns_series, horizon_bars=20, num_sims=1000, seed=42):
    """
    Saatlik log/yüzde getirilerden Monte Carlo simülasyonu:
    - horizon_bars: 20 saatlik (20 bar) ileri projeksiyon
    - num_sims: 1000 simülasyon yolu
    """
    recent = returns_series.dropna().tail(200).to_numpy(dtype=float)
    if len(recent) < 30:
        return None

    rng = np.random.default_rng(seed)
    sampled = rng.choice(recent, size=(num_sims, horizon_bars), replace=True)
    # Kümülatif getiri yolu: prod(1 + r) - 1
    path_returns = np.prod(1.0 + sampled, axis=1) - 1.0

    mean_ret_pct = float(np.mean(path_returns) * 100.0)
    win_rate_pct = float(np.mean(path_returns > 0.0) * 100.0)
    # %5 alt kuyruk -> %95 güven seviyesinde kötü senaryo (VaR)
    var_95_pct = float(np.percentile(path_returns, 5) * 100.0)

    return {
        "mean_pct": round(mean_ret_pct, 2),
        "win_pct": round(win_rate_pct, 1),
        "var95_pct": round(var_95_pct, 2)
    }

def clean_data(df):
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.loc[:, ~df.columns.duplicated()]
    return df

# ==================== BİST 1H TARAMA DÖNGÜSÜ ====================
def scan_bist_1h():
    while True:
        try:
            print("--- BIST 100 (1H) EMA50 + RSI14 + ADX14 Taramasi Baslatiliyor ---", flush=True)
            scanned_count = 0
            signals_found = 0
            all_returns = []
            kelly_scores = []

            for ticker in BIST_HISSELERI:
                try:
                    data_1h = yf.download(ticker, period=DATA_PERIOD, interval=TIMEFRAME, progress=False, threads=False)
                    data_1h = clean_data(data_1h)

                    if data_1h.empty or len(data_1h) < 60 or 'Close' not in data_1h.columns:
                        continue

                    scanned_count += 1

                    # İndikatörler: EMA 50 + RSI 14 + ADX 14 (+ ATR/Hacim/Destek-Direnç)
                    data_1h['EMA50'] = data_1h['Close'].ewm(span=50, adjust=False).mean()
                    data_1h['RSI14'] = calculate_rsi(data_1h, period=14)
                    data_1h['ADX14'] = calculate_adx(data_1h, period=14)
                    data_1h['ATR14'] = calculate_atr(data_1h, period=14)
                    data_1h['Vol_SMA20'] = data_1h['Volume'].rolling(window=20).mean()
                    data_1h['Ret'] = data_1h['Close'].pct_change()

                    all_returns.append(data_1h['Ret'].dropna().tail(150))

                    last = data_1h.iloc[-1]
                    prev = data_1h.iloc[-2]

                    close_price = float(last['Close'])
                    prev_close = float(prev['Close'])
                    ema50_val = float(last['EMA50'])
                    prev_ema50 = float(prev['EMA50'])
                    rsi_val = float(last['RSI14'])
                    adx_val = float(last['ADX14'])
                    atr_val = float(last['ATR14'])

                    if close_price <= 0 or atr_val <= 0:
                        continue

                    kelly_pct, win_p, payoff_b = calculate_kelly_fraction(data_1h['Ret'])
                    if kelly_pct > 0:
                        kelly_scores.append((ticker, kelly_pct))

                    support = round(float(data_1h['Low'].tail(20).min()), 2)
                    resistance = round(float(data_1h['High'].tail(20).max()), 2)
                    volume_confirmed = bool(last['Volume'] > last['Vol_SMA20'])
                    adx_trend_ok = adx_val >= 20.0

                    # --- 🟢 1H AL SİNYALİ (EMA 50 + RSI 14 + ADX 14) ---
                    ema50_cross_up = (prev_close <= prev_ema50) and (close_price > ema50_val)
                    rsi_buy_ok = 45.0 <= rsi_val <= 65.0

                    if ema50_cross_up and rsi_buy_ok and adx_trend_ok and volume_confirmed:
                        signals_found += 1
                        entry_price = round(close_price, 2)
                        sp = round(entry_price - (1.5 * atr_val), 2)
                        tp = round(entry_price + (3.0 * atr_val), 2)

                        message = (
                            f"🟢 *BİST 1H - AL SİNYALİ (EMA50 + RSI14 + ADX14)*\n\n"
                            f"📌 **Hisse:** `{ticker}`\n"
                            f"💰 **Giriş Fiyatı:** `{entry_price} TL`\n"
                            f"🎯 **TP (Hedef):** `{tp} TL` | 🛑 **SP:** `{sp} TL`\n"
                            f"🛡 **Destek:** `{support} TL` | ⚡ **Direnç:** `{resistance} TL`\n"
                            f"📐 **EMA50:** `{round(ema50_val, 2)}` | **RSI14:** `{round(rsi_val, 1)}` | **ADX14:** `{round(adx_val, 1)}`\n"
                            f"🎲 **Yarım-Kelly:** `%{kelly_pct}` *(Win: %{win_p}, R/R: {payoff_b})*"
                        )
                        send_telegram_message(message)

                    # --- 🔴 1H SAT SİNYALİ (EMA 50 + RSI 14 + ADX 14) ---
                    ema50_cross_down = (prev_close >= prev_ema50) and (close_price < ema50_val)
                    rsi_sell_ok = 35.0 <= rsi_val <= 55.0

                    if ema50_cross_down and rsi_sell_ok and adx_trend_ok and volume_confirmed:
                        signals_found += 1
                        entry_price = round(close_price, 2)
                        sp = round(entry_price + (1.5 * atr_val), 2)
                        tp = round(entry_price - (3.0 * atr_val), 2)

                        message = (
                            f"🔴 *BİST 1H - SAT SİNYALİ (EMA50 + RSI14 + ADX14)*\n\n"
                            f"📌 **Hisse:** `{ticker}`\n"
                            f"💰 **Giriş Fiyatı:** `{entry_price} TL`\n"
                            f"🎯 **TP (Hedef):** `{tp} TL` | 🛑 **SP:** `{sp} TL`\n"
                            f"🛡 **Destek:** `{support} TL` | ⚡ **Direnç:** `{resistance} TL`\n"
                            f"📐 **EMA50:** `{round(ema50_val, 2)}` | **RSI14:** `{round(rsi_val, 1)}` | **ADX14:** `{round(adx_val, 1)}`\n"
                            f"🎲 **Yarım-Kelly:** `%{kelly_pct}` *(Win: %{win_p}, R/R: {payoff_b})*"
                        )
                        send_telegram_message(message)

                except Exception:
                    continue

            # Genel Piyasa Monte Carlo & Kelly Özeti
            mc_text = "Veri yetersiz"
            avg_kelly_text = "%0.0"
            if all_returns:
                combined_ret = pd.concat(all_returns, ignore_index=True)
                mc = run_monte_carlo(combined_ret, horizon_bars=20, num_sims=1000)
                if mc:
                    mc_text = (
                        f"Ort. 20s Getiri: `%{mc['mean_pct']}` | "
                        f"Pozitif İhtimal: `%{mc['win_pct']}` | "
                        f"%95 VaR: `%{mc['var95_pct']}`"
                    )
            if kelly_scores:
                avg_k = round(float(np.mean([k[1] for k in kelly_scores])), 2)
                top_k = sorted(kelly_scores, key=lambda x: x[1], reverse=True)[:3]
                top_str = ", ".join([f"{t.replace('.IS','')} (%{v})" for t, v in top_k])
                avg_kelly_text = f"Ort. Yarım-Kelly: `%{avg_k}` | En Yüksek: `{top_str}`"

            summary_msg = (
                f"📊 *BİST 100 ÖZET RAPORU (1H)*\n\n"
                f"🕒 Zaman: `{datetime.now().strftime('%d-%m-%Y %H:%M')}`\n"
                f"🔍 Taranan Hisse: `{scanned_count}` | 🎯 Sinyal: `{signals_found}`\n"
                f"📈 *Filtreler:* `EMA 50 + RSI 14 + ADX 14 (>=20)`\n"
                f"🎲 *Kelly:* {avg_kelly_text}\n"
                f"🎰 *Monte Carlo (1000x20s):* {mc_text}"
            )
            send_telegram_message(summary_msg)
        except Exception as e:
            print(f"Tarama dongusu hatasi: {e}", flush=True)

        time.sleep(SCAN_INTERVAL_SEC)

# ==================== Ana Çalıştırma ====================
if __name__ == "__main__":
    threading.Thread(target=scan_bist_1h, daemon=True).start()
    run_web_server()
