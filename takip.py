import datetime as dt
import html as html_lib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    from pywebpush import WebPushException, webpush
    WEBPUSH_AVAILABLE = True
except Exception:
    WEBPUSH_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uwxfrbljvmwtxecnqgrl.supabase.co").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
RESEND_KEY = os.environ.get("RESEND_KEY", "")
SCRAPER_KEY = os.environ.get("SCRAPER_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE", "")
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "mailto:bildirim@rafta.net")
PROXY_SERVER = os.environ.get("PROXY_SERVER", "")
PROXY_USERNAME = os.environ.get("PROXY_USERNAME", "")
PROXY_PASSWORD = os.environ.get("PROXY_PASSWORD", "")
PLAYWRIGHT_FALLBACK = os.environ.get("PLAYWRIGHT_FALLBACK", "false").lower() == "true"
MAX_PRODUCTS_PER_RUN = int(os.environ.get("MAX_PRODUCTS_PER_RUN", "40"))

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_price(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw)
    text = html_lib.unescape(text)
    text = text.replace("TL", "").replace("TRY", "").replace("₺", "")
    text = re.sub(r"[^\d,.]", "", text).strip()
    if not text:
        return None
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        parts = text.split(",")
        if len(parts[-1]) <= 2:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "." in text:
        parts = text.split(".")
        if len(parts[-1]) > 2:
            text = text.replace(".", "")
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value > 0 else None


def format_price(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    parsed = urllib.parse.urlsplit(url)
    keep_params = {
        "merchantId", "boutiqueId", "colorId", "sizeId", "v1", "sku", "variant", "pid", "productId"
    }
    query = []
    for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        lk = k.lower()
        if lk.startswith("utm_") or lk in {"gclid", "fbclid", "yclid", "utm", "adjust_t", "adjust_campaign"}:
            continue
        if k in keep_params:
            query.append((k, v))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, urllib.parse.urlencode(query), ""))


def product_domain(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().replace("www.", "")


def build_scraperapi_url(target_url: str, api_key: Optional[str] = None, render_js: bool = False, premium: bool = False) -> str:
    key = api_key if api_key is not None else SCRAPER_KEY
    params = {
        "api_key": key,
        "url": target_url,
        "render": "true" if render_js else "false",
        "country_code": "tr",
    }
    if premium:
        params["premium"] = "true"
    return "http://api.scraperapi.com?" + urllib.parse.urlencode(params)


def http_json(url: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=payload, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8")
        return json.loads(body) if body else None


def http_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
        return raw.decode(enc, errors="ignore")


def fetch_direct(url: str) -> Tuple[Optional[str], str]:
    try:
        return http_text(url, timeout=25), "direct"
    except Exception as e:
        print("Direkt fetch basarisiz:", type(e).__name__, str(e)[:160])
        return None, "direct_failed"


def fetch_scraperapi(url: str, render_js: bool = False, premium: bool = False) -> Tuple[Optional[str], str]:
    if not SCRAPER_KEY:
        return None, "scraperapi_missing_key"
    mode = f"scraperapi_render_{render_js}_premium_{premium}"
    try:
        return http_text(build_scraperapi_url(url, render_js=render_js, premium=premium), timeout=75), mode
    except Exception as e:
        print(mode, "basarisiz:", type(e).__name__, str(e)[:160])
        return None, mode + "_failed"


def fetch_playwright(url: str) -> Tuple[Optional[str], str]:
    if not (PLAYWRIGHT_AVAILABLE and PLAYWRIGHT_FALLBACK):
        return None, "playwright_disabled"
    try:
        with sync_playwright() as p:
            launch_kwargs: Dict[str, Any] = {"headless": True}
            if PROXY_SERVER:
                proxy: Dict[str, str] = {"server": PROXY_SERVER}
                if PROXY_USERNAME:
                    proxy["username"] = PROXY_USERNAME
                if PROXY_PASSWORD:
                    proxy["password"] = PROXY_PASSWORD
                launch_kwargs["proxy"] = proxy
            browser = p.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                user_agent=UA_MOBILE,
                viewport={"width": 390, "height": 844},
                locale="tr-TR",
                timezone_id="Europe/Istanbul",
                is_mobile=True,
                has_touch=True,
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            content = page.content()
            browser.close()
            return content, "playwright_proxy" if PROXY_SERVER else "playwright_direct"
    except Exception as e:
        print("Playwright basarisiz:", type(e).__name__, str(e)[:160])
        return None, "playwright_failed"


def iter_json_ld(html: str) -> Iterable[Any]:
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        raw = html_lib.unescape(re.sub(r"<!--|-->", "", m.group(1))).strip()
        try:
            yield json.loads(raw)
        except Exception:
            continue


def walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for item in value:
            yield from walk_json(item)


def extract_product_data(html: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not html:
        return None, None

    name = None
    price_value = None

    for block in iter_json_ld(html):
        for obj in walk_json(block):
            obj_type = obj.get("@type") or obj.get("type")
            if isinstance(obj_type, list):
                is_product = any(str(x).lower() == "product" for x in obj_type)
            else:
                is_product = str(obj_type).lower() == "product"
            if is_product:
                name = name or obj.get("name")
                offers = obj.get("offers")
                offers_list = offers if isinstance(offers, list) else [offers]
                for offer in offers_list:
                    if isinstance(offer, dict):
                        price_value = parse_price(offer.get("price") or offer.get("lowPrice") or offer.get("highPrice"))
                        if price_value:
                            return format_price(price_value), clean_name(name)

    patterns = [
        r'"discountedPrice"\s*:\s*"?([\d.,]+)"?',
        r'"sellingPrice"\s*:\s*"?([\d.,]+)"?',
        r'"salePrice"\s*:\s*"?([\d.,]+)"?',
        r'"price"\s*:\s*"?([\d.,]+)"?',
        r'property=["\']product:price:amount["\'][^>]+content=["\']([\d.,]+)["\']',
        r'itemprop=["\']price["\'][^>]+content=["\']([\d.,]+)["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.I)
        if m:
            price_value = parse_price(m.group(1))
            if price_value:
                break

    if not price_value:
        for pattern in [
            r'(\d{1,3}(?:\.\d{3})+,\d{2})\s*(?:TL|₺)',
            r'(\d{3,7},\d{2})\s*(?:TL|₺)',
            r'(?:TL|₺)\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        ]:
            matches = re.findall(pattern, html, re.I)
            for candidate in matches[:10]:
                value = parse_price(candidate)
                if value and value > 1:
                    price_value = value
                    break
            if price_value:
                break

    if not name:
        for pattern in [
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']{3,180})["\']',
            r'<h1[^>]*>(.*?)</h1>',
            r'<title>(.*?)</title>',
            r'"name"\s*:\s*"([^"\\]{5,180})"',
        ]:
            m = re.search(pattern, html, re.I | re.S)
            if m:
                name = re.sub(r"<[^>]+>", " ", m.group(1))
                break

    return (format_price(price_value) if price_value else None), clean_name(name)


def clean_name(name: Any) -> Optional[str]:
    if not name:
        return None
    text = html_lib.unescape(str(name))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*[|—-]\s*(Trendyol|Hepsiburada|Amazon|Bershka|Zara|Rafta).*$", "", text, flags=re.I)
    return text[:180] if text else None


def resolve_short_url(url: str) -> str:
    if "ty.gl" not in url:
        return url
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA_MOBILE})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.url
    except Exception as e:
        print("Kisa URL cozulemedi:", e)
        return url


def fetch_product_data(url: str) -> Tuple[Optional[str], Optional[str], str]:
    url = normalize_url(resolve_short_url(url))
    domain = product_domain(url)
    attempts = []

    # 1) En ucuz: direkt HTML. Birçok site JSON-LD/metadan fiyat verir.
    attempts.append(fetch_direct(url))

    # 2) Ucuz proxy: JS render yok, premium yok.
    attempts.append(fetch_scraperapi(url, render_js=False, premium=False))

    # 3) Daha pahalı: premium proxy ama JS render hâlâ yok.
    if any(x in domain for x in ["trendyol.com", "amazon.", "zara.com", "bershka.com"]):
        attempts.append(fetch_scraperapi(url, render_js=False, premium=True))

    # 4) En pahalı ScraperAPI: render.
    attempts.append(fetch_scraperapi(url, render_js=True, premium=True))

    # 5) Son çare: Playwright. Varsayılan kapalı; PLAYWRIGHT_FALLBACK=true gerekir.
    attempts.append(fetch_playwright(url))

    last_mode = "none"
    for html, mode in attempts:
        last_mode = mode
        price, name = extract_product_data(html)
        print("Deneme:", mode, "price=", price, "name=", name)
        if price:
            return price, name, mode
    return None, None, last_mode


def supabase_headers(content_type: bool = False) -> Dict[str, str]:
    if not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_KEY environment variable eksik")
    headers = {"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY}
    if content_type:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal"
    return headers


def supabase_get(path: str) -> Any:
    return http_json(SUPABASE_URL + path, headers=supabase_headers())


def supabase_patch(path: str, data: Dict[str, Any]) -> None:
    http_json(SUPABASE_URL + path, method="PATCH", data=data, headers=supabase_headers(True))


def supabase_post(path: str, data: Dict[str, Any]) -> None:
    http_json(SUPABASE_URL + path, method="POST", data=data, headers=supabase_headers(True))


def safe_patch_product(urun_id: Any, data: Dict[str, Any]) -> None:
    path = "/rest/v1/urunler?id=eq." + urllib.parse.quote(str(urun_id))
    payload = dict(data)
    tried_payloads = []

    while payload:
        tried_payloads.append(set(payload.keys()))
        try:
            supabase_patch(path, payload)
            return
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            print("PATCH alanlarla basarisiz:", e.code, body[:300])

            missing = re.search(r"Could not find the ['\"]([^'\"]+)['\"] column", body)
            if missing:
                missing_col = missing.group(1)
                if missing_col in payload:
                    print("Supabase semasinda olmayan kolon atlandi:", missing_col)
                    payload.pop(missing_col, None)
                    continue

            # Eski/dar semalar için en güvenli minimum güncelleme.
            minimal = {k: v for k, v in payload.items() if k in {"son_fiyat", "urun_adi", "guncelleme_istegi"}}
            if minimal and set(minimal.keys()) not in tried_payloads and minimal != payload:
                payload = minimal
                continue
            raise

    print("PATCH atlandi: yazilacak uyumlu kolon kalmadi", urun_id)


def should_skip_product(urun: Dict[str, Any]) -> bool:
    if urun.get("guncelleme_istegi"):
        return False
    hata_sayisi = int(urun.get("hata_sayisi") or 0)
    if hata_sayisi <= 0:
        return False
    son = urun.get("son_kontrol") or urun.get("updated_at")
    if not son:
        return False
    try:
        son_dt = dt.datetime.fromisoformat(str(son).replace("Z", "+00:00"))
    except Exception:
        return False
    if son_dt.tzinfo is None:
        son_dt = son_dt.replace(tzinfo=dt.timezone.utc)
    wait_hours = min(24, 6 * hata_sayisi)
    return dt.datetime.now(dt.timezone.utc) < son_dt + dt.timedelta(hours=wait_hours)


def urunleri_getir() -> list:
    params = "select=*&satin_alindi=is.false&order=guncelleme_istegi.desc,id.desc&limit=" + str(MAX_PRODUCTS_PER_RUN)
    try:
        return supabase_get("/rest/v1/urunler?" + params) or []
    except urllib.error.HTTPError:
        # Eski şemada satin_alindi yoksa tüm ürünleri çek.
        return supabase_get("/rest/v1/urunler?select=*&order=id.desc&limit=" + str(MAX_PRODUCTS_PER_RUN)) or []


def gecmise_kaydet(urun_id: Any, fiyat: str) -> None:
    try:
        supabase_post("/rest/v1/fiyat_gecmisi", {"urun_id": urun_id, "fiyat": fiyat})
    except Exception as e:
        print("Fiyat gecmisi yazilamadi:", e)


def email_gonder(email: str, urun_adi: str, eski_fiyat: Any, yeni_fiyat: str, url: str) -> None:
    if not RESEND_KEY:
        print("RESEND_KEY yok; email atlandi")
        return
    safe_name = html_lib.escape(urun_adi or "Ürün")
    safe_url = html_lib.escape(url)
    html_body = (
        f"<h2>Fiyat düştü!</h2><p><b>{safe_name}</b> fiyatı değişti.</p>"
        f"<p>Eski fiyat: <s>{html_lib.escape(str(eski_fiyat or '-'))}</s></p>"
        f"<p>Yeni fiyat: <b style='color:green'>{html_lib.escape(str(yeni_fiyat))}</b></p>"
        f"<a href='{safe_url}' style='background:#111;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;display:inline-block;margin-top:12px'>Ürüne Git</a>"
    )
    data = {"from": "bildirim@rafta.net", "to": email, "subject": "Fiyat düştü: " + (urun_adi or "Ürün"), "html": html_body}
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(data).encode("utf-8"),
        method="POST",
        headers={"Authorization": "Bearer " + RESEND_KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("Email durumu:", r.status)
    except Exception as e:
        print("Email hatasi:", e)


def push_subscriptions_getir(email: str) -> list:
    try:
        return supabase_get("/rest/v1/push_subscriptions?email=eq." + urllib.parse.quote(email) + "&select=subscription") or []
    except Exception as e:
        print("Push subscription okunamadi:", e)
        return []


def push_gonder(email: str, title: str, body: str, url: str) -> None:
    if not (WEBPUSH_AVAILABLE and VAPID_PRIVATE):
        print("Push atlandi: pywebpush veya VAPID_PRIVATE eksik")
        return
    for sub in push_subscriptions_getir(email):
        try:
            webpush(
                subscription_info=sub["subscription"],
                data=json.dumps({"title": title, "body": body, "url": url}),
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims={"sub": VAPID_EMAIL},
            )
            print("Push gonderildi:", email)
        except WebPushException as e:
            print("Push WebPush hatasi:", repr(e))
        except Exception as e:
            print("Push genel hatasi:", repr(e))


def kontrol_et(urun: Dict[str, Any]) -> None:
    urun_id = urun["id"]
    url = urun["url"]
    email = urun.get("email")
    eski_fiyat = urun.get("son_fiyat")
    urun_adi = urun.get("urun_adi")

    if should_skip_product(urun):
        print("Backoff nedeniyle atlandi:", urun_id, url)
        return

    print("Kontrol ediliyor:", urun_id, url)
    yeni_fiyat, yeni_adi, mode = fetch_product_data(url)
    update_base = {"son_kontrol": now_iso(), "scrape_yontemi": mode}

    if not yeni_fiyat:
        hata_sayisi = int(urun.get("hata_sayisi") or 0) + 1
        safe_patch_product(urun_id, {**update_base, "hata_sayisi": hata_sayisi, "son_hata": "Fiyat çekilemedi", "guncelleme_istegi": False})
        print("Fiyat cekilemedi:", url)
        return

    yeni_adi = yeni_adi or urun_adi
    update_data = {**update_base, "son_fiyat": yeni_fiyat, "hata_sayisi": 0, "son_hata": None, "guncelleme_istegi": False}
    if yeni_adi:
        update_data["urun_adi"] = yeni_adi
    if not urun.get("ilk_fiyat"):
        update_data["ilk_fiyat"] = yeni_fiyat

    gecmise_kaydet(urun_id, yeni_fiyat)
    safe_patch_product(urun_id, update_data)
    print("Guncellendi:", eski_fiyat, "->", yeni_fiyat, "mode=", mode)

    eski_sayi = parse_price(eski_fiyat)
    yeni_sayi = parse_price(yeni_fiyat)
    fiyat_dustu = eski_sayi is not None and yeni_sayi is not None and yeni_sayi < eski_sayi
    hedef_fiyat = parse_price(urun.get("hedef_fiyat"))

    if email and fiyat_dustu and urun.get("bildirim_dusus", False):
        email_gonder(email, yeni_adi or "Ürün", eski_fiyat, yeni_fiyat, url)
        push_gonder(email, "Fiyat düştü!", f"{yeni_adi or 'Ürün'}: {yeni_fiyat}", url)

    if email and hedef_fiyat and yeni_sayi and yeni_sayi <= hedef_fiyat and urun.get("bildirim_hedef", True):
        email_gonder(email, yeni_adi or "Ürün", eski_fiyat or "-", yeni_fiyat + " (hedef fiyata ulaşıldı)", url)
        push_gonder(email, "Hedefe ulaştı!", f"{yeni_adi or 'Ürün'} hedef fiyata ulaştı: {yeni_fiyat}", url)


def main() -> None:
    urunler = urunleri_getir()
    print(f"{len(urunler)} urun bulundu.")
    for urun in urunler:
        try:
            kontrol_et(urun)
        except Exception as e:
            print("Urun hatasi:", urun.get("id"), urun.get("url"), type(e).__name__, e)
            try:
                safe_patch_product(urun.get("id"), {"son_kontrol": now_iso(), "son_hata": str(e)[:240], "hata_sayisi": int(urun.get("hata_sayisi") or 0) + 1, "guncelleme_istegi": False})
            except Exception as patch_e:
                print("Hata bilgisi yazilamadi:", patch_e)
        time.sleep(1)


if __name__ == "__main__":
    main()
