from playwright.sync_api import sync_playwright
import time
import requests
from urllib.parse import quote
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uwxfrbljvmwtxecnqgrl.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_L567-kgj8bZmK6uhMABbkA_VwhqrGCn")
RESEND_KEY = os.environ.get("RESEND_KEY", "re_4Q6m5BmF_BibZvq3izfs193Huzhy2tj26")

def fiyat_cek(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(8)
        try:
            fiyat = page.locator(".new-price").first.inner_text()
        except:
            fiyat = None
        browser.close()
        return fiyat

def fiyat_getir(url):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    r = requests.get(f"{SUPABASE_URL}/rest/v1/urunler?select=son_fiyat", headers=headers)
    data = r.json()
    if data and len(data) > 0:
        return data[0]["son_fiyat"]
    return None

def fiyat_guncelle(url, yeni_fiyat):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    requests.patch(f"{SUPABASE_URL}/rest/v1/urunler?url=eq.{quote(url, safe='')}", json={"son_fiyat": yeni_fiyat}, headers=headers)

def email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url):
    headers = {
        "Authorization": f"Bearer {RESEND_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "from": "onboarding@resend.dev",
        "to": email,
        "subject": f"Fiyat dustu: {urun_adi}",
        "html": f"<h2>Fiyat Dusus Bildirimi</h2><p><b>{urun_adi}</b> urununde fiyat dususu tespit edildi!</p><p>Eski fiyat: <s>{eski_fiyat}</s></p><p>Yeni fiyat: <b style='color:green'>{yeni_fiyat}</b></p><a href='{url}' style='background:orange;color:white;padding:10px 20px;text-decoration:none;border-radius:5px'>Urun sayfasina git</a>"
    }
    r = requests.post("https://api.resend.com/emails", json=data, headers=headers)
    if r.status_code == 200:
        print("Email gonderildi!")
    else:
        print("Email hatasi:", r.text)

def kontrol_et(url, urun_adi, email):
    print(f"Kontrol ediliyor: {urun_adi}")
    yeni_fiyat = fiyat_cek(url)
    if not yeni_fiyat:
        print("Fiyat cekilemedi.")
        return
    eski_fiyat = fiyat_getir(url)
    print(f"Eski: {eski_fiyat} - Yeni: {yeni_fiyat}")
    if eski_fiyat and eski_fiyat != yeni_fiyat:
        print("Fiyat degisti! Email gonderiliyor...")
        email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url)
    else:
        print("Fiyat degismedi.")
    fiyat_guncelle(url, yeni_fiyat)

urunler = [
    {
        "url": "https://www.trendyol.com/kron/tx-75-p-772835371",
        "urun_adi": "Kron TX 75 Bisiklet",
        "email": "aykutkadiruzun@gmail.com"
    }
]

for urun in urunler:
    kontrol_et(urun["url"], urun["urun_adi"], urun["email"])
