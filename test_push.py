import os
import json
from pywebpush import webpush, WebPushException
import urllib.request
import urllib.parse

SUPABASE_URL = "https://uwxfrbljvmwtxecnqgrl.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE", "aDUEzHzPJ5-w1LuFElyE-tGuaQhD-0PD4Rydv5fZlfY")
VAPID_EMAIL = "mailto:bildirim@rafta.net"
TEST_EMAIL = "aykutkadiruzun@gmail.com"

def http_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": "Bearer " + SUPABASE_KEY
}

subs = http_get(
    SUPABASE_URL + "/rest/v1/push_subscriptions?email=eq." + urllib.parse.quote(TEST_EMAIL) + "&select=subscription",
    headers
)

print("Subscription sayisi:", len(subs))

for sub in subs:
    try:
        webpush(
            subscription_info=sub["subscription"],
            data=json.dumps({
                "title": "Test Bildirimi 🔔",
                "body": "Push bildirimi çalışıyor!",
                "url": "https://rafta.net"
            }),
            vapid_private_key=VAPID_PRIVATE,
            vapid_claims={"sub": VAPID_EMAIL}
        )
        print("Push gonderildi!")
    except WebPushException as e:
        print("Push hatasi:", repr(e))
    except Exception as e:
        print("Genel hata:", repr(e))
