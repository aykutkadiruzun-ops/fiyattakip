from playwright.sync_api import sync_playwright
import time
import os
import json
import re
import urllib.request
import urllib.parse

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uwxfrbljvmwtxecnqgrl.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
RESEND_KEY = os.environ.get("RESEND_KEY", "re_4Q6m5BmF_BibZvq3izfs193Huzhy2tj26")
SCRAPER_KEY = os.environ.get("SCRAPER_KEY", "e69fb8c04518138c28881d88931b8e14")

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

def scraper_get(target_url, render_js=True):
    params = {
        "api_key": SCRAPER_KEY,
        "url": target_url,
        "render": "true" if render_js else "false",
        "premium": "true",
        "country_code": "tr",
    }
    api_url = "http://api.scraperapi.com?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")

# ── TRENDYOL ──────────────────────────────────────────────────
def trendyol_fiyat_ve_adi(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(8)

            fiyat = None
            for sel in [".new-price", ".prc-box-dscntd", ".product-price-container"]:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0:
                        fiyat = el.inner_text().strip()
                        break
                except:
                    pass

            urun_adi = None
            try:
                urun_adi = page.locator("h1.pr-new-br span").first.inner_text().strip()
            except:
                try:
                    urun_adi = page.locator("h1").first.inner_text().strip()
                except:
                    pass

            browser.close()
            return fiyat, urun_adi
    except Exception as e:
        print("Trendyol hatasi:", e)
        return None, None

# ── SCRAPER API İLE DİĞER SİTELER ────────────────────────────
def genel_fiyat_ve_adi(url):
    try:
        content = scraper_get(url, render_js=True)
        fiyat = None
        matches = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:TL|₺)', content)
        if matches:
            fiyat = matches[0] + " TL"
        if not fiyat:
            matches2 = re.findall(r'"price":\s*"?([\d.,]+)"?', content)
            if matches2:
                try:
                    fiyat = f"{float(matches2[0]):,.2f}".replace(",", ".") + " TL"
                except:
                    pass
        urun_adi = None
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', content)
        if m:
            urun_adi = m.group(1).strip()
        return fiyat, urun_adi
    except Exception as e:
        print("Genel scraper hatasi:", e)
        return None, None

# ── SUPABASE ──────────────────────────────────────────────────
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
        "from": "bildirim@rafta.net",
        "to": email,
        "subject": "Fiyat dustu: " + (urun_adi or "Urun"),
        "html": html
    }
    status = http_post("https://api.resend.com/emails", headers, data)
    print("Email durumu:", status)

# ── ANA KONTROL FONKSİYONU ────────────────────────────────────
def kontrol_et(urun):
    urun_id = urun["id"]
    url = urun["url"]
    email = urun["email"]
    eski_fiyat = urun.get("son_fiyat")
    urun_adi = urun.get("urun_adi")

    print("Kontrol ediliyor:", url)

    yeni_fiyat = None
    yeni_adi = None

    if "trendyol.com" in url:
        yeni_fiyat, yeni_adi = trendyol_fiyat_ve_adi(url)
    else:
        yeni_fiyat, yeni_adi = genel_fiyat_ve_adi(url)

    if not urun_adi and yeni_adi:
        urun_adi = yeni_adi

    if not yeni_fiyat:
        print("Fiyat cekilemedi:", url)
        return

    print("Eski:", eski_fiyat, "-> Yeni:", yeni_fiyat)

    gecmise_kaydet(urun_id, yeni_fiyat)
    fiyat_guncelle(urun_id, yeni_fiyat, urun_adi)

    if eski_fiyat and eski_fiyat != yeni_fiyat:
        print("Fiyat degisti! Email gonderiliyor...")
        email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url)
    else:
        print("Fiyat degismedi.")

    hedef_fiyat = urun.get("hedef_fiyat")
    if hedef_fiyat:
        try:
            yeni_sayi = float(re.sub(r'[^\d,]', '', yeni_fiyat).replace(',', '.'))
            if yeni_sayi <= float(hedef_fiyat):
                print("Hedef fiyata ulasildi!")
                email_gonder(email, urun_adi, eski_fiyat or "-", yeni_fiyat + " (HEDEF FIYATA ULASILDI!)", url)
        except Exception as e:
            print("Hedef fiyat kontrolu hatasi:", e)

# ── CALISTIR ──────────────────────────────────────────────────
urunler = urunleri_getir()
print(f"{len(urunler)} urun bulundu.")
for urun in urunler:
    try:
        kontrol_et(urun)
    except Exception as e:
        print("Hata:", urun.get("url"), "-", e)
