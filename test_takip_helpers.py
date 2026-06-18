import urllib.error
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def test_parse_price_tr_formats():
    from takip import parse_price
    assert parse_price("1.234,56 TL") == 1234.56
    assert parse_price("₺999,90") == 999.90
    assert parse_price("1299 TL") == 1299.0
    assert parse_price(None) is None


def test_should_use_expensive_fetch_respects_backoff():
    from takip import should_skip_product
    assert should_skip_product({"hata_sayisi": 0, "sonraki_kontrol": None}) is False
    assert should_skip_product({"hata_sayisi": 3, "sonraki_kontrol": "2099-01-01T00:00:00+00:00"}) is True
    assert should_skip_product({"guncelleme_istegi": True, "hata_sayisi": 9, "sonraki_kontrol": "2099-01-01T00:00:00+00:00"}) is False


def test_build_scraperapi_url_defaults_are_cheap():
    from takip import build_scraperapi_url
    api_url = build_scraperapi_url("https://example.com/p/1", api_key="KEY", render_js=False, premium=False)
    assert "api_key=KEY" in api_url
    assert "render=false" in api_url
    assert "premium=true" not in api_url
    assert "country_code=tr" in api_url


def test_extract_product_data_from_json_ld():
    from takip import extract_product_data
    html = '''
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"Test Ayakkabı","offers":{"price":"1234.56","priceCurrency":"TRY"}}
    </script></head></html>
    '''
    price, name = extract_product_data(html)
    assert price == "1.234,56 TL"
    assert name == "Test Ayakkabı"


def test_extract_trendyol_content_id_from_url():
    from takip import extract_trendyol_content_id

    assert extract_trendyol_content_id("https://www.trendyol.com/marka/urun-adi-p-1124000210?merchantId=123") == "1124000210"
    assert extract_trendyol_content_id("https://www.trendyol.com/sr?q=abc") is None


def test_extract_trendyol_api_product_data():
    from takip import extract_trendyol_api_product_data

    payload = {
        "result": {
            "name": "Retinol Bakuchiol Body Lotion",
            "price": {"discountedPrice": {"text": "249,90 TL"}},
        }
    }
    assert extract_trendyol_api_product_data(payload) == ("249,90 TL", "Retinol Bakuchiol Body Lotion")



def test_safe_patch_product_retries_without_missing_supabase_columns(monkeypatch=None):
    import takip

    calls = []

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self, body):
            super().__init__("url", 400, "Bad Request", None, None)
            self._body = body.encode("utf-8")

        def read(self):
            return self._body

    def fake_patch(path, data):
        calls.append(dict(data))
        if "hata_sayisi" in data:
            raise FakeHTTPError('{"message":"Could not find the \'hata_sayisi\' column of \'urunler\' in the schema cache"}')
        if "son_kontrol" in data:
            raise FakeHTTPError('{"message":"Could not find the \'son_kontrol\' column of \'urunler\' in the schema cache"}')

    old_patch = takip.supabase_patch
    old_missing = set(getattr(takip, "MISSING_SUPABASE_COLUMNS", set()))
    takip.supabase_patch = fake_patch
    takip.MISSING_SUPABASE_COLUMNS.clear()
    try:
        takip.safe_patch_product(1, {
            "son_fiyat": "729,95 TL",
            "urun_adi": "Test",
            "hata_sayisi": 0,
            "son_kontrol": "2026-01-01T00:00:00+00:00",
            "guncelleme_istegi": False,
        })
    finally:
        takip.supabase_patch = old_patch
        takip.MISSING_SUPABASE_COLUMNS.clear()
        takip.MISSING_SUPABASE_COLUMNS.update(old_missing)

    assert len(calls) == 3
    assert "hata_sayisi" not in calls[-1]
    assert "son_kontrol" not in calls[-1]
    assert calls[-1]["son_fiyat"] == "729,95 TL"


def test_safe_patch_product_remembers_missing_columns_for_next_product():
    import takip

    calls = []
    old_patch = takip.supabase_patch
    old_missing = set(getattr(takip, "MISSING_SUPABASE_COLUMNS", set()))
    takip.MISSING_SUPABASE_COLUMNS.clear()
    takip.MISSING_SUPABASE_COLUMNS.update({"hata_sayisi", "son_kontrol"})

    def fake_patch(path, data):
        calls.append(dict(data))

    takip.supabase_patch = fake_patch
    try:
        takip.safe_patch_product(2, {
            "son_fiyat": "729,95 TL",
            "hata_sayisi": 0,
            "son_kontrol": "2026-01-01T00:00:00+00:00",
            "guncelleme_istegi": False,
        })
    finally:
        takip.supabase_patch = old_patch
        takip.MISSING_SUPABASE_COLUMNS.clear()
        takip.MISSING_SUPABASE_COLUMNS.update(old_missing)

    assert len(calls) == 1
    assert calls[0] == {"son_fiyat": "729,95 TL", "guncelleme_istegi": False}


def test_scraperapi_403_disables_more_scraper_calls():
    import takip

    calls = []

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("url", 403, "Forbidden", None, None)

    def fake_http_text(url, timeout=25):
        calls.append(url)
        raise FakeHTTPError()

    old_text = takip.http_text
    old_disabled = takip.SCRAPERAPI_DISABLED
    old_key = takip.SCRAPER_KEY
    takip.http_text = fake_http_text
    takip.SCRAPERAPI_DISABLED = False
    takip.SCRAPER_KEY = "KEY"
    try:
        assert takip.fetch_scraperapi("https://example.com/p1")[1].endswith("_forbidden")
        assert takip.fetch_scraperapi("https://example.com/p2")[1] == "scraperapi_disabled_after_403"
    finally:
        takip.http_text = old_text
        takip.SCRAPERAPI_DISABLED = old_disabled
        takip.SCRAPER_KEY = old_key

    assert len(calls) == 1


def test_next_check_hours_success_and_failure_backoff():
    from takip import next_check_iso

    success = next_check_iso(success=True, hata_sayisi=0, now="2026-01-01T00:00:00+00:00")
    first_fail = next_check_iso(success=False, hata_sayisi=1, now="2026-01-01T00:00:00+00:00")
    many_fail = next_check_iso(success=False, hata_sayisi=5, now="2026-01-01T00:00:00+00:00")

    assert success == "2026-01-01T06:00:00+00:00"
    assert first_fail == "2026-01-01T06:00:00+00:00"
    assert many_fail == "2026-01-04T00:00:00+00:00"


def test_should_skip_product_respects_next_check_and_purchased():
    import takip

    old_force = takip.FORCE_CHECK_ALL
    try:
        takip.FORCE_CHECK_ALL = False
        assert takip.should_skip_product({"satin_alindi": True, "guncelleme_istegi": True}) is True
        assert takip.should_skip_product({"sonraki_kontrol": "2099-01-01T00:00:00+00:00"}) is True
        assert takip.should_skip_product({"guncelleme_istegi": True, "sonraki_kontrol": "2099-01-01T00:00:00+00:00"}) is False

        takip.FORCE_CHECK_ALL = True
        assert takip.should_skip_product({"sonraki_kontrol": "2099-01-01T00:00:00+00:00"}) is False
        assert takip.should_skip_product({"satin_alindi": True, "sonraki_kontrol": None}) is True
    finally:
        takip.FORCE_CHECK_ALL = old_force


def test_due_products_query_filters_by_next_check():
    from takip import build_due_products_path

    path = build_due_products_path(now="2026-01-01T00:00:00+00:00", limit=25)
    assert "satin_alindi=is.false" in path
    assert "guncelleme_istegi.is.true" in path
    assert "sonraki_kontrol.lte.2026-01-01T00%3A00%3A00%2B00%3A00" in path
    assert "limit=25" in path


def test_force_all_products_query_ignores_next_check():
    from takip import build_all_active_products_path

    path = build_all_active_products_path(limit=25)
    assert "satin_alindi=is.false" in path
    assert "sonraki_kontrol" not in path
    assert "limit=25" in path


def test_force_check_all_does_not_skip_future_next_check():
    import takip

    old_force = takip.FORCE_CHECK_ALL
    calls = []
    takip.FORCE_CHECK_ALL = True
    try:
        def fake_fetch(url):
            calls.append(url)
            return None, None, "test"
        old_fetch = takip.fetch_product_data
        old_patch = takip.safe_patch_product
        takip.fetch_product_data = fake_fetch
        takip.safe_patch_product = lambda urun_id, data: None
        try:
            takip.kontrol_et({
                "id": 99,
                "url": "https://example.com/p",
                "sonraki_kontrol": "2099-01-01T00:00:00+00:00",
                "satin_alindi": False,
            })
        finally:
            takip.fetch_product_data = old_fetch
            takip.safe_patch_product = old_patch
    finally:
        takip.FORCE_CHECK_ALL = old_force

    assert calls == ["https://example.com/p"]


def test_extract_browser_fallback_url_from_trendyol_intent_redirect():
    from takip import extract_browser_fallback_url

    intent = (
        "intent://123456?source=seller_store"
        "#Intent;scheme=https;package=trendyol.com;"
        "S.browser_fallback_url=https%3A%2F%2Fwww.trendyol.com%2Fgenel-tedarik%2Fkabartma-desenli-p-123456%3FmerchantId%3D123;end"
    )
    assert extract_browser_fallback_url(intent) == "https://www.trendyol.com/genel-tedarik/kabartma-desenli-p-123456?merchantId=123"


def test_notification_event_key_is_stable_and_price_specific():
    from takip import notification_event_key

    assert notification_event_key(12, "price_drop", 729.95) == "12:price_drop:729.95"
    assert notification_event_key(12, "target_reached", 1000) == "12:target_reached:1000.00"


def test_should_send_notification_false_when_log_exists():
    import takip

    calls = []
    old_get = takip.supabase_get

    def fake_get(path):
        calls.append(path)
        return [{"id": 1}]

    takip.supabase_get = fake_get
    try:
        assert takip.should_send_notification(1, "price_drop", "1:price_drop:729.95") is False
    finally:
        takip.supabase_get = old_get

    assert "bildirim_loglari" in calls[0]
    assert "event_key=eq.1%3Aprice_drop%3A729.95" in calls[0]


def test_should_send_notification_true_when_log_missing():
    import takip

    old_get = takip.supabase_get
    takip.supabase_get = lambda path: []
    try:
        assert takip.should_send_notification(1, "price_drop", "1:price_drop:729.95") is True
    finally:
        takip.supabase_get = old_get


def test_log_notification_writes_event_key():
    import takip

    calls = []
    old_post = takip.supabase_post
    takip.supabase_post = lambda path, data: calls.append((path, data))
    try:
        takip.log_notification(1, "u@example.com", "price_drop", "1:price_drop:729.95", "729,95 TL")
    finally:
        takip.supabase_post = old_post

    assert calls[0][0] == "/rest/v1/bildirim_loglari"
    assert calls[0][1]["event_key"] == "1:price_drop:729.95"
    assert calls[0][1]["fiyat"] == "729,95 TL"


def test_extract_trendyol_embedded_json_price_and_name():
    from takip import extract_product_data

    html = r'''
    <html><body>
    <script>
    window.__PRODUCT_DETAIL_APP_INITIAL_STATE__ = {
      "product": {
        "name": "Kabarna Desenli Premium Elbise",
        "price": {"discountedPrice": {"text": "899,99 TL", "value": 899.99}},
        "variants": []
      }
    };
    </script>
    </body></html>
    '''
    price, name = extract_product_data(html)
    assert price == "899,99 TL"
    assert name == "Kabarna Desenli Premium Elbise"


def test_extract_trendyol_price_value_currency_pattern():
    from takip import extract_product_data

    html = '<script>{"price":{"value":1299.95,"currency":"TRY"},"name":"Currency Pattern Ürün"}</script>'
    price, name = extract_product_data(html)
    assert price == "1.299,95 TL"
    assert name == "Currency Pattern Ürün"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
