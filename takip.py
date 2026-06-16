from playwright.sync_api import sync_playwright
import time
import os
import json
import re
import urllib.request
import urllib.parse
try:
    from pywebpush import webpush, WebPushException
    WEBPUSH_AVAILABLE = True
    print("pywebpush yuklu, push aktif")
except ImportError:
    WEBPUSH_AVAILABLE = False
    print("pywebpush yuklu degil, push bildirimleri devre disi")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uwxfrbljvmwtxecnqgrl.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
RESEND_KEY = os.environ.get("RESEND_KEY", "re_4Q6m5BmF_BibZvq3izfs193Huzhy2tj26")
SCRAPER_KEY = os.environ.get("SCRAPER_KEY", "e69fb8c04518138c28881d88931b8e14")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE", "dkt52zrQhGw_LKL-tcGCOzUoogHjReokrNWdTbY1k70")
VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC", "BF9hdpEtHLXh-FwVuinhb6Mo0xUOt2PQqx2bn12GLNrz6FBPNeNqR9pFUMXC3__Aq6Q2oHgb5iNK1a2dX8HqFZ4")
VAPID_EMAIL = "mailto:bildirim@rafta.net"

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

def trendyol_fiyat_ve_adi(url):
    return trendyol_playwright(url)

def trendyol_playwright(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
                viewport={"width": 390, "height": 844},
                locale="tr-TR",
                timezone_id="Europe/Istanbul",
                is_mobile=True,
                has_touch=True,
            )
            page = context.new_page()
            # ty.gl kısa linkini çöz
            if "ty.gl" in url:
                try:
                    req = urllib.request.Request(url, method='HEAD')
                    with urllib.request.urlopen(req) as r:
                        url = r.url
                    print("Redirect sonrası URL:", url)
                except Exception as e:
                    print("Redirect hatasi:", e)
            mobile_url = url.replace("www.trendyol.com", "m.trendyol.com")
            page.goto(mobile_url, wait_until="networkidle", timeout=60000)
            time.sleep(15)
            try:
                content = page.content()
                print("Sayfa uzunlugu:", len(content))
                print("Sayfa icerigi (ilk 500):", content[:500])
            except:
                pass

            fiyat = None
            for sel in [".prc-box-dscntd", ".prc-box-sllng", ".new-price", ".product-price-container", ".price-container", ".pr-bx-nm"]:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0:
                        text = el.inner_text().strip()
                        if text and any(c.isdigit() for c in text):
                            fiyat = text
                            print("Fiyat bulundu:", fiyat)
                            break
                except:
                    pass

            if not fiyat:
                try:
                    content = page.content()
                    m = re.search(r'"discountedPrice"\s*:\s*([\d.]+)', content)
                    if not m:
                        m = re.search(r'"price"\s*:\s*([\d.]+)', content)
                    if m:
                        val = float(m.group(1))
                        if val > 1:
                            fiyat = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"
                            print("Fiyat JSON'dan bulundu:", fiyat)
                except:
                    pass

            urun_adi = None
            try:
                urun_adi = page.locator("h1").first.inner_text().strip()
            except:
                pass

            browser.close()
            return fiyat, urun_adi
    except Exception as e:
        print("Trendyol Playwright hatasi:", e)
        return None, None

def genel_fiyat_ve_adi(url):
    try:
        content = scraper_get(url, render_js=True)
        fiyat = None

        def parse_fiyat(raw):
            if '.' in raw and ',' in raw:
                raw = raw.replace('.', '').replace(',', '.')
            elif ',' in raw:
                parts = raw.split(',')
                if len(parts[-1]) <= 2:
                    raw = raw.replace(',', '.')
                else:
                    raw = raw.replace(',', '')
            elif '.' in raw and len(raw.split('.')[-1]) > 2:
                raw = raw.replace('.', '')
            try:
                return float(raw)
            except:
                return None

        m = re.search(r'"price"\s*:\s*"?([\d.,]+)"?', content)
        if m:
            val = parse_fiyat(m.group(1))
            if val and val > 1:
                fiyat = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"

        if not fiyat:
            matches = re.findall(r'(\d{1,3}(?:\.\d{3})+,\d{2})\s*(?:TL|₺)', content)
            if matches:
                val = parse_fiyat(matches[0])
                if val and val > 1:
                    fiyat = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"

        if not fiyat:
            matches = re.findall(r'(\d{3,6},\d{2})\s*(?:TL|₺)', content)
            if matches:
                val = parse_fiyat(matches[0])
                if val and val > 1:
                    fiyat = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"

        if not fiyat:
            matches = re.findall(r'(\d{2,6})\s*(?:TL|₺)', content)
            if matches:
                val = float(matches[0])
                if val > 1:
                    fiyat = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"

        urun_adi = None
        for pattern in [r'<h1[^>]*class="[^"]*product[^"]*"[^>]*>([^<]+)</h1>',
                        r'"name"\s*:\s*"([^"]{5,100})"',
                        r'<h1[^>]*>([^<]{5,100})</h1>',
                        r'<title>([^|<-]{5,80})']:
            m2 = re.search(pattern, content)
            if m2:
                urun_adi = m2.group(1).strip()
                break

        return fiyat, urun_adi
    except Exception as e:
        print("Genel scraper hatasi:", e)
        return None, None

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

def push_subscriptions_getir(email):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY
    }
    try:
        result = http_get(
            SUPABASE_URL + "/rest/v1/push_subscriptions?email=eq." + urllib.parse.quote(email) + "&select=subscription",
            headers
        )
        print("Subscription sorgu sonucu:", result)
        return result
    except Exception as e:
        print("Subscription getirme hatasi:", e)
        return []

def email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url):
    try:
        headers = {
            "Authorization": "Bearer " + RESEND_KEY,
            "Content-Type": "application/json"
        }
        html = (
            "<h2>Fiyat Dustu!</h2>"
            "<p><b>" + (urun_adi or "Urun") + "</b> fiyati degisti!</p>"
            "<p>Eski fiyat: <s>" + str(eski_fiyat) + "</s></p>"
            "<p>Yeni fiyat: <b style='color:green'>" + str(yeni_fiyat) + "</b></p>"
            "<a href='" + url + "' style='background:#111;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;display:inline-block;margin-top:12px'>Urune Git</a>"
        )
        data = {
            "from": "bildirim@rafta.net",
            "to": email,
            "subject": "Fiyat dustu: " + (urun_adi or "Urun"),
            "html": html
        }
        status = http_post("https://api.resend.com/emails", headers, data)
        print("Email durumu:", status)
    except Exception as e:
        print("Email hatasi (devam ediliyor):", e)

def push_gonder(email, title, body, url):
    if not WEBPUSH_AVAILABLE:
        print("pywebpush yuklu degil")
        return
    print("Push deneniyor:", email)
    subscriptions = push_subscriptions_getir(email)
    print("Subscription sayisi:", len(subscriptions))
    if not subscriptions:
        print("Push subscription bulunamadi:", email)
        return
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub["subscription"],
                data=json.dumps({"title": title, "body": body, "url": url}),
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims={"sub": VAPID_EMAIL}
            )
            print("Push gonderildi:", email)
        except WebPushException as e:
            print("Push WebPush hatasi:", repr(e))
        except Exception as e:
            print("Push genel hatasi:", repr(e))

def kontrol_et(urun):
    urun_id = urun["id"]
    url = urun["url"]
    email = urun["email"]
    eski_fiyat = urun.get("son_fiyat")
    urun_adi = urun.get("urun_adi")

    print("Kontrol ediliyor:", url)

    yeni_fiyat = None
    yeni_adi = None

    if "trendyol.com" in url or "ty.gl" in url:
        yeni_fiyat, yeni_adi = trendyol_fiyat_ve_adi(url)
    else:
        yeni_fiyat, yeni_adi = genel_fiyat_ve_adi(url)

    if yeni_adi:
        urun_adi = yeni_adi

    if not yeni_fiyat:
        print("Fiyat cekilemedi:", url)
        return

    print("Eski:", eski_fiyat, "-> Yeni:", yeni_fiyat)

    gecmise_kaydet(urun_id, yeni_fiyat)
    fiyat_guncelle(urun_id, yeni_fiyat, urun_adi)

    bildirim_dusus = urun.get("bildirim_dusus", False)
    bildirim_hedef = urun.get("bildirim_hedef", True)

    fiyat_dustu = eski_fiyat and eski_fiyat != yeni_fiyat

    if fiyat_dustu:
        print("Fiyat degisti!")
        if bildirim_dusus:
            print("Her dusus bildirimi aktif, bildirim gonderiliyor...")
            email_gonder(email, urun_adi, eski_fiyat, yeni_fiyat, url)
            push_gonder(email, "Fiyat dustu!", f"{urun_adi or 'Urun'}: {yeni_fiyat}", url)
    else:
        print("Fiyat degismedi.")

    hedef_fiyat = urun.get("hedef_fiyat")
    if hedef_fiyat and bildirim_hedef:
        try:
            yeni_sayi = float(re.sub(r'[^\d,]', '', yeni_fiyat).replace(',', '.'))
            if yeni_sayi <= float(hedef_fiyat):
                print("Hedef fiyata ulasildi! Bildirim gonderiliyor...")
                email_gonder(email, urun_adi, eski_fiyat or "-", yeni_fiyat + " (HEDEF FIYATA ULASILDI!)", url)
                push_gonder(email, "Hedefe ulasti!", f"{urun_adi or 'Urun'} hedef fiyata ulasti: {yeni_fiyat}", url)
        except Exception as e:
            print("Hedef fiyat kontrolu hatasi:", e)

urunler = urunleri_getir()
print(f"{len(urunler)} urun bulundu.")

istekli = [u for u in urunler if u.get("guncelleme_istegi")]
diger   = [u for u in urunler if not u.get("guncelleme_istegi")]

if istekli:
    print(f"{len(istekli)} urun icin manuel guncelleme istegi var.")

for urun in istekli + diger:
    try:
        kontrol_et(urun)
        if urun.get("guncelleme_istegi"):
            headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": "Bearer " + SUPABASE_KEY,
                "Content-Type": "application/json"
            }
            http_patch(
                SUPABASE_URL + "/rest/v1/urunler?id=eq." + str(urun["id"]),
                headers,
                {"guncelleme_istegi": False}
            )
    except Exception as e:
        print("Hata:", urun.get("url"), "-", e)
