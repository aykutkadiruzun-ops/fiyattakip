from playwright.sync_api import sync_playwright
import time
import os
import json
import urllib.request
import urllib.parse

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uwxfrbljvmwtxecnqgrl.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_L567-kgj8bZmK6uhMABbkA_VwhqrGCn")
RESEND_KEY = os.environ.get("RESEND_KEY", "re_4Q6m5BmF_BibZvq3izfs193Huzhy2tj26")

def http_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

def http_post(url, headers, data):
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except Exception as e:
        print("POST hatasi:", e)
        return 0

def http_patch(url, headers, data):
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except Exception as e:
        print("PATCH hatasi:", e)
        return 0

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
            fiyat = fiyat.strip()
        except:
            fiyat = None
        browser.close()
        return fiyat

def fiyat_getir():
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY
    }
    data = http_get(SUPABASE_URL + "/rest/v1/urunler?select=son_fiyat", headers)
    if data and len(data) > 0:
        return data[0]["son_fiyat"]
    return None

def fiyat_guncelle(yeni_fiyat):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    http_patch(SUPABASE_URL + "/rest/v1/urunler?id=eq.1", headers, {"son_fiyat": yeni_fiyat})

def email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url):
    headers = {
        "Authorization": "Bearer " + RESEND_KEY,
        "Content-Type": "application/json"
    }
    html = "<h2>Fiyat Dusus</h2><p>" + urun_adi + " fiyati degisti!</p><p>Eski: " + eski_fiyat + "</p><p>Yeni: " + yeni_fiyat + "</p><a href='" + url + "'>Urune Git</a>"
    data = {
        "from": "onboarding@resend.dev",
        "to": email,
        "subject": "Fiyat dustu: " + urun_adi,
        "html": html
    }
    status = http_post("https://api.resend.com/emails", headers, data)
    if status == 200:
        print("Email gonderildi!")
    else:
        print("Email durumu:", status)

def kontrol_et(url, urun_adi, email):
    print("Kontrol ediliyor: " + urun_adi)
    yeni_fiyat = fiyat_cek(url)
    if not yeni_fiyat:
        print("Fiyat cekilemedi.")
        return
    eski_fiyat = fiyat_getir()
    print("Eski: " + str(eski_fiyat) + " - Yeni: " + str(yeni_fiyat))
    if eski_fiyat and eski_fiyat != yeni_fiyat:
        print("Fiyat degisti!")
        email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url)
    else:
        print("Fiyat degismedi.")
    fiyat_guncelle(yeni_fiyat)

urunler = [
    {
        "url": "https://www.trendyol.com/kron/tx-75-p-772835371",
        "urun_adi": "Kron TX 75 Bisiklet",
        "email": "aykutkadiruzun@gmail.com"
    }
]

for urun in urunler:
    kontrol_et(urun["url"], urun["urun_adi"], urun["email"])
