import { createClient } from "jsr:@supabase/supabase-js@2";

const SCRAPER_KEY = Deno.env.get("SCRAPER_KEY") || "e69fb8c04518138c28881d88931b8e14";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "https://uwxfrbljvmwtxecnqgrl.supabase.co";
const SUPABASE_KEY = Deno.env.get("SERVICE_KEY") || "";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { urun_id } = await req.json();
    if (!urun_id) return Response.json({ error: "urun_id gerekli" }, { status: 400, headers: corsHeaders });

    const sb = createClient(SUPABASE_URL, SUPABASE_KEY);
    const { data: urun } = await sb.from("urunler").select("*").eq("id", urun_id).single();
    if (!urun) return Response.json({ error: "Ürün bulunamadı" }, { status: 404, headers: corsHeaders });

    if (urun.url.includes("trendyol.com")) {
      return Response.json({ message: "Trendyol için sonraki zamanlanmış güncelleme bekleniyor." }, { headers: corsHeaders });
    }

    const params = new URLSearchParams({
      api_key: SCRAPER_KEY,
      url: urun.url,
      render: "true",
      premium: "true",
      country_code: "tr",
    });
    const res = await fetch(`http://api.scraperapi.com?${params}`);
    const html = await res.text();

    let fiyat: string | null = null;
    let urun_adi: string | null = null;

    const priceMatch = html.match(/"price"\s*:\s*"?([\d.,]+)"?/);
    if (priceMatch) {
      let raw = priceMatch[1];
      if (raw.includes(".") && raw.includes(",")) raw = raw.replace(/\./g, "").replace(",", ".");
      else if (raw.includes(",")) raw = raw.replace(",", ".");
      const val = parseFloat(raw);
      if (val > 1) fiyat = val.toLocaleString("tr-TR", { minimumFractionDigits: 2 }) + " TL";
    }

    if (!fiyat) {
      const matches = html.match(/(\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:TL|₺)/);
      if (matches) fiyat = matches[1] + " TL";
    }

    const nameMatch = html.match(/<h1[^>]*>([^<]{5,100})<\/h1>/);
    if (nameMatch) urun_adi = nameMatch[1].trim();

    // Mail gönder — fiyattan bağımsız, her zaman
    const RESEND_KEY = Deno.env.get("RESEND_KEY") || "";
    if (RESEND_KEY && urun.email) {
      const isIlkFiyat = !urun.son_fiyat;
      const subject = isIlkFiyat
        ? `🎉 Rafta'ya kaydedildi: ${urun_adi || "Ürün"}`
        : `📉 Fiyat güncellendi: ${urun_adi || "Ürün"}`;
      const fiyatBlock = fiyat
        ? `<div style="background:#EBF4E5;border-radius:14px;padding:14px;margin:16px 0"><div style="font-size:11px;color:#2D6A2D;text-transform:uppercase">Güncel fiyat</div><div style="font-size:26px;font-weight:800;color:#2D6A2D">${fiyat}</div></div>`
        : `<div style="background:#F6F3EA;border-radius:14px;padding:14px;margin:16px 0;color:#3A3428;font-size:14px">Ürün bilgileri alınıyor. İlk fiyat kontrolünden sonra güncellenecek.</div>`;
      const htmlBody = `<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;padding:28px 18px;background:#FAFAF8"><div style="font-size:24px;font-weight:700;margin-bottom:18px">rafta<span style="color:#888">.</span></div><div style="background:#fff;border:1px solid #E8E6DF;border-radius:20px;padding:24px"><h1 style="font-size:22px;margin:0 0 10px">${isIlkFiyat ? "🎉 Rafta'ya kaydedildi" : "📉 Fiyat güncellendi"}</h1><p style="color:#555;font-size:15px">${urun_adi || "Ürün"}</p>${fiyatBlock}<a href="${urun.url}" style="display:block;text-align:center;background:#111;color:#fff;text-decoration:none;padding:14px;border-radius:12px;font-weight:700">Ürünü görüntüle</a><p style="font-size:12px;color:#888;margin-top:16px">Bu bildirim Rafta fiyat takip tercihlerine göre gönderildi.</p></div></div>`;
      await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: { "Authorization": "Bearer " + RESEND_KEY, "Content-Type": "application/json" },
        body: JSON.stringify({ from: "bildirim@rafta.net", to: urun.email, subject, html: htmlBody }),
      });
    }

    if (fiyat) {
      const updateData: Record<string, unknown> = { son_fiyat: fiyat, guncelleme_istegi: false };
      if (urun_adi) updateData.urun_adi = urun_adi;
      await sb.from("urunler").update(updateData).eq("id", urun_id);
      await sb.from("fiyat_gecmisi").insert({ urun_id, fiyat });
      return Response.json({ success: true, fiyat }, { headers: corsHeaders });
    } else {
      return Response.json({ message: "Fiyat çekilemedi." }, { headers: corsHeaders });
    }
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500, headers: corsHeaders });
  }
});
