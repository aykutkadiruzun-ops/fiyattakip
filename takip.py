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

def urunleri_getir():
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY
    }
    return http_get(SUPABASE_URL + "/rest/v1/urunler?select=*", headers)

def fiyat_guncelle(urun_id, yeni_fiyat, urun_adi):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    data = {"son_fiyat": yeni_fiyat}
    if urun_adi:
        data["urun_adi"] = urun_adi
    http_patch(
        SUPABASE_URL + "/rest/v1/urunler?id=eq." + str(urun_id),
        headers,
        data
    )

def gecmise_kaydet(urun_id, fiyat):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    http_post(
        SUPABASE_URL + "/rest/v1/fiyat_gecmisi",
        headers,
        {"urun_id": urun_id, "fiyat": fiyat}
    )

def urun_adi_cek(page):
    try:
        return page.locator("h1.pr-new-br span").first.inner_text().strip()
    except:
        try:
            return page.locator("h1").first.inner_text().strip()
        except:
            return None

def email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url):
    headers = {
        "Authorization": "Bearer " + RESEND_KEY,
        "Content-Type": "application/json"
    }
    html = (
        "<h2>💸 Fiyat Dustu!</h2>"
        "<p><b>" + (urun_adi or "Urun") + "</b> fiyati degisti!</p>"
        "<p>Eski fiyat: <s>" + str(eski_fiyat) + "</s></p>"
        "<p>Yeni fiyat: <b style='color:green'>" + str(yeni_fiyat) + "</b></p>"
        "<a href='" + url + "' style='background:#534AB7;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;display:inline-block;margin-top:12px'>Urune Git</a>"
    )
    data = {
        "from": "onboarding@resend.dev",
        "to": email,
        "subject": "Fiyat dustu: " + (urun_adi or "Urun"),
        "html": html
    }
    status = http_post("https://api.resend.com/emails", headers, data)
    print("Email durumu:", status)

def kontrol_et(urun):
    urun_id = urun["id"]
    url = urun["url"]
    email = urun["email"]
    eski_fiyat = urun.get("son_fiyat")
    urun_adi = urun.get("urun_adi") or url

    print("Kontrol ediliyor:", url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(8)

        # Fiyat cek
        yeni_fiyat = None
        try:
            yeni_fiyat = page.locator(".new-price").first.inner_text().strip()
        except:
            pass

        # Urun adi cek (ilk kontrolde)
        if not urun.get("urun_adi"):
            try:
                urun_adi = page.locator("h1.pr-new-br span").first.inner_text().strip()
            except:
                try:
                    urun_adi = page.locator("h1").first.inner_text().strip()
                except:
                    urun_adi = None

        browser.close()

    if not yeni_fiyat:
        print("Fiyat cekilemedi:", url)
        return

    print("Eski:", eski_fiyat, "-> Yeni:", yeni_fiyat)

    # Fiyat gecmisine kaydet
    gecmise_kaydet(urun_id, yeni_fiyat)

    # Supabase guncelle
    fiyat_guncelle(urun_id, yeni_fiyat, urun_adi)

   # Fiyat dustuyse email gonder
    if eski_fiyat and eski_fiyat != yeni_fiyat:
        print("Fiyat degisti! Email gonderiliyor...")
        email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url)
    else:
        print("Fiyat degismedi.")

    # Hedef fiyata ulastiysa email gonder
    hedef_fiyat = urun.get("hedef_fiyat")
    if hedef_fiyat:
        try:
            yeni_sayi = float(yeni_fiyat.replace("TL","").replace(".","").replace(",",".").strip())
            if yeni_sayi <= float(hedef_fiyat):
                print("Hedef fiyata ulasildi! Email gonderiliyor...")
                email_gonder(email, urun_adi, eski_fiyat or "-", yeni_fiyat + " (HEDEF FIYATA ULASILDI!)", url)
        except Exception as e:
            print("Hedef fiyat kontrolu hatasi:", e)

# Tum urunleri Supabase'den cek ve kontrol et
urunler = urunleri_getir()
print(f"{len(urunler)} urun bulundu.")
for urun in urunler:
    try:
        kontrol_et(urun)
    except Exception as e:
        print("Hata:", urun.get("url"), "-", e)
