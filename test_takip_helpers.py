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
    assert should_skip_product({"hata_sayisi": 0, "son_kontrol": None}) is False
    assert should_skip_product({"hata_sayisi": 3, "son_kontrol": "2099-01-01T00:00:00"}) is True
    assert should_skip_product({"guncelleme_istegi": True, "hata_sayisi": 9, "son_kontrol": "2099-01-01T00:00:00"}) is False


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


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
