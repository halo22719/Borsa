import os
import time
import json
import datetime
import requests
import pandas as pd
import yfinance as yf

# Render üzerindeki Environment Variables'tan bilgileri alır
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HISSELER = ["THYAO", "GARAN", "EREGL", "ASELS", "TUPRS"]
PORTFOY_DOSYASI = "portfoy.json"

STOP_LOSS_ORAN = 0.02   # %2 Zarar Kes
TAKE_PROFIT_ORAN = 0.04 # %4 Kar Al

def telegram_mesaj_gonder(mesaj):
    if not TOKEN or not CHAT_ID:
        print("TOKEN veya CHAT_ID eksik!")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram mesaj hatası: {e}")

def portfoy_oku():
    if not os.path.exists(PORTFOY_DOSYASI):
        return {}
    try:
        with open(PORTFOY_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def portfoy_yaz(data):
    with open(PORTFOY_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def hisse_analiz_et(hisse_kodu):
    symbol = f"{hisse_kodu}.IS"
    try:
        df = yf.download(tickers=symbol, period="5d", interval="30m", progress=False)
        if df.empty or len(df) < 20:
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['SMA20'] = df['Close'].rolling(window=20).mean()

        son_fiyat = float(df['Close'].iloc[-1])
        o_anki_sma = float(df['SMA20'].iloc[-1])
        bir_onceki_fiyat = float(df['Close'].iloc[-2])
        bir_onceki_sma = float(df['SMA20'].iloc[-2])

        zaman_str = datetime.datetime.now().strftime("%H:%M")
        portfoy = portfoy_oku()

        # Pozisyon Kontrolü
        if hisse_kodu in portfoy:
            maliyet = portfoy[hisse_kodu]["maliyet"]
            stop_fiyat = maliyet * (1 - STOP_LOSS_ORAN)
            kar_fiyat = maliyet * (1 + TAKE_PROFIT_ORAN)

            if son_fiyat <= stop_fiyat:
                zarar_yuzde = ((son_fiyat - maliyet) / maliyet) * 100
                mesaj = f"🛑 *STOP-LOSS TETİKLENDİ!*\n\n*Hisse:* #{hisse_kodu}\n*Maliyet:* {maliyet:.2f} TL\n*Fiyat:* {son_fiyat:.2f} TL (%{zarar_yuzde:.2f})"
                telegram_mesaj_gonder(mesaj)
                del portfoy[hisse_kodu]
                portfoy_yaz(portfoy)
            elif son_fiyat >= kar_fiyat:
                kar_yuzde = ((son_fiyat - maliyet) / maliyet) * 100
                mesaj = f"🎯 *KAR AL TETİKLENDİ!*\n\n*Hisse:* #{hisse_kodu}\n*Maliyet:* {maliyet:.2f} TL\n*Fiyat:* {son_fiyat:.2f} TL (+%{kar_yuzde:.2f})"
                telegram_mesaj_gonder(mesaj)
                del portfoy[hisse_kodu]
                portfoy_yaz(portfoy)
            elif bir_onceki_fiyat > bir_onceki_sma and son_fiyat < o_anki_sma:
                mesaj = f"🔴 *SAT / TREND KIRILIMI!*\n\n*Hisse:* #{hisse_kodu}\n*Fiyat:* {son_fiyat:.2f} TL"
                telegram_mesaj_gonder(mesaj)
                del portfoy[hisse_kodu]
                portfoy_yaz(portfoy)
        else:
            if bir_onceki_fiyat < bir_onceki_sma and son_fiyat > o_anki_sma:
                mesaj = f"🟢 *AL SİNYALİ!*\n\n*Hisse:* #{hisse_kodu}\n*Giriş Fiyatı:* {son_fiyat:.2f} TL\n*Saat:* {zaman_str}"
                telegram_mesaj_gonder(mesaj)
                portfoy[hisse_kodu] = {"maliyet": son_fiyat, "tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
                portfoy_yaz(portfoy)
    except Exception as e:
        print(f"{hisse_kodu} hatası: {e}")

if __name__ == "__main__":
    print("Bot 7/24 döngüde başlatıldı...")
    while True:
        now = datetime.datetime.now()
        # Hafta içi ve BIST seans saatleri (10:00 - 18:30) kontrolü
        if now.weekday() < 5 and 10 <= now.hour <= 18:
            print(f"[{now.strftime('%H:%M:%S')}] Tarama yapılıyor...")
            for hisse in HISSELER:
                hisse_analiz_et(hisse)
        time.sleep(1800) # 30 dakikada bir tarar
