import { createClient } from "jsr:@supabase/supabase-js@2";

const SCRAPER_KEY = Deno.env.get("SCRAPER_KEY");
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "https://uwxfrbljvmwtxecnqgrl.supabase.co";
const SERVICE_KEY = Deno.env.get("SERVICE_KEY") || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const RESEND_KEY = Deno.env.get("RESEND_KEY") || "";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

type Product = {
  id: number;
  url: string;
  email: string;
  urun_adi?: string | null;
  son_fiyat?: string | null;
  hedef_fiyat?: string | number | null;
  bildirim_dusus?: boolean | null;
};

function jsonResponse(body: Record<string, unknown>, status = 200) {
  return Response.json(body, { status, headers: corsHeaders });
}

function parsePrice(raw: unknown): number | null {
  if (raw === null || raw === undefined) return null;
  let text = String(raw).replace(/TL|TRY|₺/gi, "");
  text = text.replace(/[^\d,.]/g, "").trim();
  if (!text) return null;
  if (text.includes(".") && text.includes(",")) text = text.replace(/\./g, "").replace(",", ".");
  else if (text.includes(",")) text = text.replace(",", ".");
  else if (text.includes(".")) {
    const parts = text.split(".");
    if ((parts.at(-1) || "").length > 2) text = text.replace(/\./g, "");
  }
  const value = Number.parseFloat(text);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function formatPrice(value: number): string {
  return value.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " TL";
}

function formatDelta(value: number): string {
  if (Math.abs(value - Math.round(value)) < 0.005) {
    return Math.round(value).toLocaleString("tr-TR") + " TL";
  }
  return formatPrice(value);
}

function compactProductName(name: unknown, limit = 58): string {
  const text = String(name || "Ürün").replace(/\s+/g, " ").trim() || "Ürün";
  return text.length <= limit ? text : text.slice(0, limit - 1).trimEnd() + "…";
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function buildMailContent(eventType: "initial_price" | "price_drop", productName: string, oldPrice: string | null, newPrice: string | null, url: string) {
  const product = compactProductName(productName);
  const oldNum = parsePrice(oldPrice);
  const newNum = parsePrice(newPrice);
  const saving = oldNum !== null && newNum !== null && oldNum > newNum ? oldNum - newNum : null;

  let subject = "";
  let headline = "";
  let body = "";
  let insight = "";

  if (eventType === "initial_price") {
    subject = `🎉 Takip başladı: ${product}`;
    headline = "Takip başladı";
    body = `${product} artık takipte.`;
    insight = newPrice ? `İlk fiyat: ${newPrice}` : "Artık bu ürünü senin yerine takip ediyoruz.";
  } else {
    const savingText = saving !== null ? formatDelta(saving) : "";
    subject = savingText ? `📉 Güzel haber: ${product} ${savingText} ucuzladı` : `📉 Güzel haber: ${product} ucuzladı`;
    headline = "Güzel haber";
    body = savingText ? `${product} bugün ${savingText} düştü.` : `${product} biraz daha ucuzladı.`;
    insight = newPrice ? `Güncel fiyat: ${newPrice}` : "Ürünü tekrar kontrol etmek mantıklı.";
  }

  const priceBlock = newPrice
    ? `<div style="background:#EBF4E5;border-radius:14px;padding:14px;margin:16px 0"><div style="font-size:11px;color:#2D6A2D;text-transform:uppercase;letter-spacing:.06em">Güncel fiyat</div><div style="font-size:26px;font-weight:800;color:#2D6A2D">${escapeHtml(newPrice)}</div></div>`
    : `<div style="background:#F6F3EA;border-radius:14px;padding:14px;margin:16px 0;color:#3A3428;font-size:14px">Ürün kaydedildi. İlk fiyat kontrolünden sonra güncellenecek.</div>`;

  const html = `<div style="margin:0;padding:0;background:#FAFAF8;font-family:Inter,Arial,sans-serif;color:#111"><div style="max-width:560px;margin:0 auto;padding:28px 18px"><div style="font-size:24px;font-weight:700;margin-bottom:18px">rafta<span style="color:#888">.</span></div><div style="background:#fff;border:1px solid #E8E6DF;border-radius:20px;padding:24px"><div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#888;margin-bottom:10px">${escapeHtml(headline)}</div><h1 style="font-size:24px;line-height:1.15;margin:0 0 10px">${escapeHtml(product)}</h1><p style="font-size:15px;line-height:1.55;color:#555;margin:0 0 16px">${escapeHtml(body)}</p>${priceBlock}<div style="background:#F6F3EA;color:#3A3428;border-radius:14px;padding:12px 14px;margin-bottom:20px;font-size:14px">${escapeHtml(insight)}</div><a href="${escapeHtml(url)}" style="display:block;text-align:center;background:#111;color:#fff;text-decoration:none;padding:15px 18px;border-radius:14px;font-weight:700">Ürünü kontrol et</a><p style="font-size:12px;color:#888;line-height:1.5;margin:18px 0 0">Bu bildirim Rafta fiyat takip tercihlerine göre gönderildi.</p></div></div></div>`;

  return { subject, html };
}

function notificationEventKey(productId: number, eventType: string, value: unknown): string {
  const numeric = parsePrice(value);
  const suffix = numeric !== null ? numeric.toFixed(2) : String(value ?? "added");
  return `${productId}:${eventType}:${suffix}`;
}

async function shouldSendNotification(sb: ReturnType<typeof createClient>, urunId: number, eventType: string, eventKey: string): Promise<boolean> {
  const { data, error } = await sb
    .from("bildirim_loglari")
    .select("id")
    .eq("urun_id", urunId)
    .eq("event_type", eventType)
    .eq("event_key", eventKey)
    .limit(1);
  if (error) {
    console.error("Bildirim log sorgusu başarısız; spam riskini önlemek için mail atlandı:", error.message);
    return false;
  }
  return !data || data.length === 0;
}

async function logNotification(sb: ReturnType<typeof createClient>, urunId: number, email: string, eventType: string, eventKey: string, fiyat: string | null) {
  const { error } = await sb.from("bildirim_loglari").insert({
    urun_id: urunId,
    email,
    event_type: eventType,
    event_key: eventKey,
    fiyat,
    fiyat_num: parsePrice(fiyat),
  });
  if (error) console.error("Bildirim logu yazılamadı:", error.message);
}

async function sendMail(email: string, eventType: "initial_price" | "price_drop", productName: string, oldPrice: string | null, newPrice: string | null, url: string) {
  if (!RESEND_KEY) {
    console.log("RESEND_KEY yok; email atlandı");
    return false;
  }
  const content = buildMailContent(eventType, productName, oldPrice, newPrice, url);
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { "Authorization": "Bearer " + RESEND_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ from: "bildirim@rafta.net", to: email, subject: content.subject, html: content.html }),
  });
  if (!res.ok) {
    console.error("Email hatası:", res.status, await res.text());
    return false;
  }
  console.log("Email gönderildi:", email, eventType);
  return true;
}

async function extractProductData(url: string): Promise<{ fiyat: string | null; urun_adi: string | null }> {
  if (!SCRAPER_KEY) throw new Error("SCRAPER_KEY eksik");
  const params = new URLSearchParams({
    api_key: SCRAPER_KEY,
    url,
    render: "true",
    premium: "true",
    country_code: "tr",
  });
  const res = await fetch(`http://api.scraperapi.com?${params}`);
  if (!res.ok) throw new Error(`ScraperAPI hata: ${res.status}`);
  const html = await res.text();

  let fiyat: string | null = null;
  let urun_adi: string | null = null;

  const priceMatch = html.match(/"price"\s*:\s*"?([\d.,]+)"?/);
  if (priceMatch) {
    const val = parsePrice(priceMatch[1]);
    if (val !== null) fiyat = formatPrice(val);
  }

  if (!fiyat) {
    const matches = html.match(/(\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:TL|₺)/);
    if (matches) fiyat = matches[1] + " TL";
  }

  const nameMatch = html.match(/<h1[^>]*>([^<]{5,100})<\/h1>/);
  if (nameMatch) urun_adi = nameMatch[1].replace(/\s+/g, " ").trim();

  return { fiyat, urun_adi };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Sadece POST desteklenir" }, 405);
  if (!SERVICE_KEY) return jsonResponse({ error: "SERVICE_KEY eksik" }, 500);
  if (!SCRAPER_KEY) return jsonResponse({ error: "SCRAPER_KEY eksik" }, 500);

  try {
    const authHeader = req.headers.get("Authorization") || "";
    const token = authHeader.replace(/^Bearer\s+/i, "").trim();
    if (!token) return jsonResponse({ error: "Kullanıcı doğrulanamadı" }, 401);

    const sb = createClient(SUPABASE_URL, SERVICE_KEY);
    const { data: authData, error: authError } = await sb.auth.getUser(token);
    const user = authData?.user;
    if (authError || !user?.email) return jsonResponse({ error: "Kullanıcı doğrulanamadı" }, 401);

    const { urun_id } = await req.json();
    if (!urun_id) return jsonResponse({ error: "urun_id gerekli" }, 400);

    const { data: urunData, error: urunError } = await sb
      .from("urunler")
      .select("*")
      .eq("id", urun_id)
      .eq("email", user.email)
      .single();
    const urun = urunData as Product | null;
    if (urunError || !urun) return jsonResponse({ error: "Ürün bulunamadı" }, 404);

    const isInitialPrice = !urun.son_fiyat;

    // Ürün ekleme maili scraper sonucuna bağlı olmamalı.
    // Kullanıcı ürünü kaydettiyse, fiyat çekilemese bile "Takip başladı" maili gider.
    if (isInitialPrice) {
      const eventType = "initial_price";
      const eventKey = notificationEventKey(urun.id, eventType, "added");
      if (await shouldSendNotification(sb, urun.id, eventType, eventKey)) {
        const sent = await sendMail(urun.email, eventType, urun.urun_adi || "Ürün", null, null, urun.url);
        if (sent) await logNotification(sb, urun.id, urun.email, eventType, eventKey, null);
      }
    }

    if (urun.url.includes("trendyol.com")) {
      return jsonResponse({ message: "Trendyol için sonraki zamanlanmış güncelleme bekleniyor." });
    }

    const { fiyat, urun_adi } = await extractProductData(urun.url);
    const oldPrice = urun.son_fiyat || null;
    const oldNum = parsePrice(oldPrice);
    const newNum = parsePrice(fiyat);
    const isPriceDrop = oldNum !== null && newNum !== null && newNum < oldNum;
    const shouldSendMail = isPriceDrop;

    if (fiyat) {
      const updateData: Record<string, unknown> = { son_fiyat: fiyat, guncelleme_istegi: false };
      if (urun_adi) updateData.urun_adi = urun_adi;
      const { error: updateError } = await sb.from("urunler").update(updateData).eq("id", urun.id).eq("email", user.email);
      if (updateError) return jsonResponse({ error: updateError.message }, 500);
      const { error: historyError } = await sb.from("fiyat_gecmisi").insert({ urun_id: urun.id, fiyat });
      if (historyError) console.error("Fiyat geçmişi yazılamadı:", historyError.message);
    }

    if (shouldSendMail) {
      const eventType: "initial_price" | "price_drop" = isInitialPrice ? "initial_price" : "price_drop";
      const eventKey = notificationEventKey(urun.id, eventType, eventType === "initial_price" ? (fiyat || "added") : fiyat);
      if (await shouldSendNotification(sb, urun.id, eventType, eventKey)) {
        const sent = await sendMail(urun.email, eventType, urun_adi || urun.urun_adi || "Ürün", oldPrice, fiyat, urun.url);
        if (sent) await logNotification(sb, urun.id, urun.email, eventType, eventKey, fiyat);
      }
    }

    if (fiyat) return jsonResponse({ success: true, fiyat, urun_adi });
    return jsonResponse({ message: "Ürün kaydedildi. Fiyat ilk zamanlanmış kontrolde tekrar denenecek." });
  } catch (e) {
    return jsonResponse({ error: e instanceof Error ? e.message : String(e) }, 500);
  }
});
