import os
import time
import logging
import threading
from datetime import datetime
import requests
import pandas as pd
import yfinance as yf
from http.server import HTTPServer, BaseHTTPRequestHandler

# Yahoo Finance gereksiz log/warning çıktılarını gizleme
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ==================== Mini Web Sunucusu (Render Keep-Alive) ====================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BIST ve Midas Kripto 5x Bot Calisiyor!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"Web sunucusu {port} portunda baslatildi.")
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==================== Bot Ayarları ====================
TELEGRAM_TOKEN = "8853048772:AAEW22ekJlDBc3EK9pWTiC8plZVm_9RBwas"
CHAT_ID = "1131754179"

LEVERAGE = 5
MARGIN_MODE = "ISOLATED"
TRADE_MARGIN_USDT = 30.0       # İşlem başına marjin (30$)
SP_MARGIN_PCT = 0.20           # Marjin üzerinden %20 SP (-6.00 USDT)
TP_MARGIN_PCT = 0.40           # Marjin üzerinden %40 TP (+12.00 USDT)

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

MIDAS_USDT_PARITELERI = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "XRPUSDT": "XRP-USD",
    "SOLUSDT": "SOL-USD",
    "AVAXUSDT": "AVAX-USD",
    "ADAUSDT": "ADA-USD",
    "DOGEUSDT": "DOGE-USD",
    "LINKUSDT": "LINK-USD",
    "DOTUSDT": "DOT-USD",
    "UNIUSDT": "UNI-USD",
    "AAVEUSDT": "AAVE-USD",
    "ARBUSDT": "ARB-USD",
    "NEARUSDT": "NEAR-USD",
    "MANAUSDT": "MANA-USD",
    "WIFUSDT": "WIF-USD",
    "RENDERUSDT": "RENDER-USD"
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

# ==================== İndikatör Hesaplamaları ====================
def calculate_atr(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def calculate_supertrend(df, period=10, multiplier=3):
    high = df['High']
    low = df['Low']
    close = df['Close']

    atr = calculate_atr(df, period=period)
    hl2 = (high + low) / 2
    basic_upperband = hl2 + (multiplier * atr)
    basic_lowerband = hl2 - (multiplier * atr)

    final_upperband = basic_upperband.copy()
    final_lowerband = basic_lowerband.copy()

    for i in range(1, len(df)):
        if basic_upperband.iloc[i] < final_upperband.iloc[i-1] or close.iloc[i-1] > final_upperband.iloc[i-1]:
            final_upperband.iloc[i] = basic_upperband.iloc[i]
        else:
            final_upperband.iloc[i] = final_upperband.iloc[i-1]

        if basic_lowerband.iloc[i] > final_lowerband.iloc[i-1] or close.iloc[i-1] < final_lowerband.iloc[i-1]:
            final_lowerband.iloc[i] = basic_lowerband.iloc[i]
        else:
            final_lowerband.iloc[i] = final_lowerband.iloc[i-1]

    supertrend = pd.Series(index=df.index, dtype='float64')
    direction = pd.Series(1, index=df.index)

    for i in range(1, len(df)):
        if close.iloc[i] > final_upperband.iloc[i-1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lowerband.iloc[i-1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i-1]

        supertrend.iloc[i] = final_lowerband.iloc[i] if direction.iloc[i] == 1 else final_upperband.iloc[i]

    return supertrend, direction

def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['Close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['Close'].ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def clean_data(df):
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.loc[:, ~df.columns.duplicated()]
    return df

def format_price(val, is_crypto=False):
    if is_crypto:
        if val >= 100:
            return round(val, 2)
        elif val >= 1:
            return round(val, 4)
        else:
            return round(val, 6)
    return round(val, 2)

# ==================== TARAMA MOTORU ====================
def analyze_symbol(display_name, yf_ticker, is_crypto=False):
    data = yf.download(yf_ticker, period="15d", interval="30m", progress=False)
    data = clean_data(data)

    if data.empty or len(data) < 50 or 'Close' not in data.columns:
        return []

    data['Supertrend'], data['ST_Direction'] = calculate_supertrend(data)
    data['RSI'] = calculate_rsi(data)
    data['MACD'], data['MACD_Signal'] = calculate_macd(data)
    data['ATR'] = calculate_atr(data)
    data['Vol_SMA20'] = data['Volume'].rolling(window=20).mean()
    data['EMA200'] = data['Close'].ewm(span=200, adjust=False).mean()

    last = data.iloc[-1]
    prev = data.iloc[-2]

    close_price = float(last['Close'])
    low_price = float(last['Low'])
    atr_val = float(last['ATR'])
    rsi_val = float(last['RSI'])
    ema200_val = float(last['EMA200'])
    macd_val = float(last['MACD'])
    macd_sig_val = float(last['MACD_Signal'])

    if close_price <= 0 or atr_val <= 0:
        return []

    support = format_price(float(data['Low'].tail(20).min()), is_crypto)
    resistance = format_price(float(data['High'].tail(20).max()), is_crypto)

    volume_confirmed = bool(last['Volume'] > last['Vol_SMA20'])
    price_change_from_low = ((close_price - low_price) / low_price) * 100
    not_overbought_today = price_change_from_low <= 4.5

    # Marjin % -> Dayanak varlık fiyat hareket %
    sp_price_move_pct = SP_MARGIN_PCT / LEVERAGE  # %20 / 5 = %4.0
    tp_price_move_pct = TP_MARGIN_PCT / LEVERAGE  # %40 / 5 = %8.0
    sp_usdt = round(TRADE_MARGIN_USDT * SP_MARGIN_PCT, 2)
    tp_usdt = round(TRADE_MARGIN_USDT * TP_MARGIN_PCT, 2)
    notional_usdt = round(TRADE_MARGIN_USDT * LEVERAGE, 2)

    alerts = []
    unit = "USDT" if is_crypto else "TL"
    entry_price = format_price(close_price, is_crypto)

    # --- 🟢 LONG / AL SİNYALİ ---
    st_buy_signal = (prev['ST_Direction'] == -1) and (last['ST_Direction'] == 1)
    ema200_buy_ok = close_price > ema200_val
    rsi_buy_ok = 45 <= rsi_val <= 60
    macd_buy_ok = macd_val > macd_sig_val

    if st_buy_signal and volume_confirmed and ema200_buy_ok and rsi_buy_ok and macd_buy_ok and not_overbought_today:
        if is_crypto:
            raw_sp = close_price * (1 - sp_price_move_pct)
            raw_tp = close_price * (1 + tp_price_move_pct)
            raw_trail = close_price * (1 + (tp_price_move_pct * 0.5))
            sp = format_price(raw_sp, True)
            tp = format_price(raw_tp, True)
            trail = format_price(raw_trail, True)

            msg = (
                f"🟢 *MİDAS FUTURES ({LEVERAGE}x İZOLE) - LONG SİNYALİ*\n\n"
                f"📌 **Parite:** `{display_name}`\n"
                f"💼 **Marjin / Büyüklük:** `{TRADE_MARGIN_USDT:.0f} USDT` (`{notional_usdt:.0f} USDT`)\n"
                f"💰 **Giriş (Entry):** `{entry_price} {unit}`\n"
                f"🎯 **TP (Hedef):** `{tp} {unit}` *(+%{TP_MARGIN_PCT*100:.0f} / `+{tp_usdt:.2f} USDT`)*\n"
                f"🛑 **SP (Stop-Loss):** `{sp} {unit}` *(-%{SP_MARGIN_PCT*100:.0f} / `-{sp_usdt:.2f} USDT`)*\n"
                f"📈 **İz Süren Tetik:** `{trail} {unit}`\n\n"
                f"🛡 **Destek:** `{support}` | ⚡ **Direnç:** `{resistance}`\n"
                f"📊 *Filtreler:* Supertrend + EMA200 + MACD + RSI (`{round(rsi_val, 1)}`)"
            )
        else:
            sp = format_price(close_price - (1.5 * atr_val), False)
            tp = format_price(close_price + (3.0 * atr_val), False)
            msg = (
                f"🟢 *BİST 30M - AKILLI ATR AL SİNYALİ*\n\n"
                f"📌 **Hisse:** `{display_name}`\n"
                f"💰 **Giriş Fiyatı:** `{entry_price} {unit}`\n"
                f"🎯 **TP (Hedef):** `{tp} {unit}`\n"
                f"🛑 **SP (Stop-Loss):** `{sp} {unit}`\n\n"
                f"🛡 **Destek:** `{support}` | ⚡ **Direnç:** `{resistance}`\n"
                f"📊 *Filtreler:* Supertrend + EMA200 + MACD + RSI (`{round(rsi_val, 1)}`)"
            )
        alerts.append(msg)

    # --- 🔴 SHORT / SAT SİNYALİ (Dip Filtreli: RSI >= 40) ---
    st_sell_signal = (prev['ST_Direction'] == 1) and (last['ST_Direction'] == -1)
    ema200_sell_ok = close_price < ema200_val
    rsi_sell_ok = 40 <= rsi_val <= 65
    macd_sell_ok = macd_val < macd_sig_val

    if st_sell_signal and volume_confirmed and ema200_sell_ok and rsi_sell_ok and macd_sell_ok:
        if is_crypto:
            raw_sp = close_price * (1 + sp_price_move_pct)
            raw_tp = close_price * (1 - tp_price_move_pct)
            raw_trail = close_price * (1 - (tp_price_move_pct * 0.5))
            sp = format_price(raw_sp, True)
            tp = format_price(raw_tp, True)
            trail = format_price(raw_trail, True)

            msg = (
                f"🔴 *MİDAS FUTURES ({LEVERAGE}x İZOLE) - SHORT SİNYALİ*\n\n"
                f"📌 **Parite:** `{display_name}`\n"
                f"💼 **Marjin / Büyüklük:** `{TRADE_MARGIN_USDT:.0f} USDT` (`{notional_usdt:.0f} USDT`)\n"
                f"💰 **Giriş (Entry):** `{entry_price} {unit}`\n"
                f"🎯 **TP (Hedef):** `{tp} {unit}` *(+%{TP_MARGIN_PCT*100:.0f} / `+{tp_usdt:.2f} USDT`)*\n"
                f"🛑 **SP (Stop-Loss):** `{sp} {unit}` *(-%{SP_MARGIN_PCT*100:.0f} / `-{sp_usdt:.2f} USDT`)*\n"
                f"📉 **İz Süren Tetik:** `{trail} {unit}`\n\n"
                f"🛡 **Destek:** `{support}` | ⚡ **Direnç:** `{resistance}`\n"
                f"📊 *Filtreler:* Supertrend SAT + EMA200 Altı + MACD + RSI (`{round(rsi_val, 1)}`)"
            )
        else:
            sp = format_price(close_price + (1.5 * atr_val), False)
            tp = format_price(close_price - (3.0 * atr_val), False)
            msg = (
                f"🔴 *BİST 30M - AKILLI ATR SAT SİNYALİ*\n\n"
                f"📌 **Hisse:** `{display_name}`\n"
                f"💰 **Giriş Fiyatı:** `{entry_price} {unit}`\n"
                f"🎯 **TP (Hedef):** `{tp} {unit}`\n"
                f"🛑 **SP (Stop-Loss):** `{sp} {unit}`\n\n"
                f"🛡 **Destek:** `{support}` | ⚡ **Direnç:** `{resistance}`\n"
                f"📊 *Filtreler:* Supertrend SAT + EMA200 Altı + MACD + RSI (`{round(rsi_val, 1)}`)"
            )
        alerts.append(msg)

    return alerts

def scan_markets():
    while True:
        print("--- BIST + Midas USDT (30$ / 5x Izole / %40 TP) Taramasi Baslatiliyor ---")
        scanned_bist = 0
        scanned_crypto = 0
        signals_found = 0

        for ticker in BIST_HISSELERI:
            try:
                msgs = analyze_symbol(ticker, ticker, is_crypto=False)
                scanned_bist += 1
                for m in msgs:
                    send_telegram_message(m)
                    signals_found += 1
            except Exception:
                continue

        for usdt_pair, yf_pair in MIDAS_USDT_PARITELERI.items():
            try:
                msgs = analyze_symbol(usdt_pair, yf_pair, is_crypto=True)
                scanned_crypto += 1
                for m in msgs:
                    send_telegram_message(m)
                    signals_found += 1
            except Exception:
                continue

        summary_msg = (
            f"📊 *BOT ÖZET RAPORU (30M)*\n\n"
            f"🕒 Zaman: `{datetime.now().strftime('%d-%m-%Y %H:%M')}`\n"
            f"📈 Taranan BİST: `{scanned_bist}` | 🪙 Midas USDT: `{scanned_crypto}`\n"
            f"🎯 Yakalanan Sinyal: `{signals_found}`\n"
            f"⚙️ Kripto Modu: `{MARGIN_MODE} {LEVERAGE}x` | Marjin: `{TRADE_MARGIN_USDT:.0f} USDT` (TP +%40 / SP -%20)"
        )
        send_telegram_message(summary_msg)
        time.sleep(1800)

# ==================== Ana Çalıştırma ====================
if __name__ == "__main__":
    threading.Thread(target=scan_markets, daemon=True).start()

    while True:
        time.sleep(60)
