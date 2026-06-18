-- Rafta fiyat takip sistemi için ölçeklenebilir takip kolonları
-- Supabase SQL Editor içine yapıştırıp Run butonuna basabilirsin.
-- Güvenlidir: IF NOT EXISTS kullanır, mevcut kolonları bozmaz.

-- 1) urunler tablosuna takip / hata / maliyet kontrol kolonları
ALTER TABLE public.urunler
  ADD COLUMN IF NOT EXISTS son_kontrol timestamptz,
  ADD COLUMN IF NOT EXISTS sonraki_kontrol timestamptz,
  ADD COLUMN IF NOT EXISTS son_basarili_kontrol timestamptz,
  ADD COLUMN IF NOT EXISTS hata_sayisi integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS son_hata text,
  ADD COLUMN IF NOT EXISTS scrape_yontemi text,
  ADD COLUMN IF NOT EXISTS son_fiyat_num numeric,
  ADD COLUMN IF NOT EXISTS ilk_fiyat_num numeric;

-- 2) fiyat_gecmisi tablosuna numeric fiyat kolonu
ALTER TABLE public.fiyat_gecmisi
  ADD COLUMN IF NOT EXISTS fiyat_num numeric;

-- 3) Aynı fiyat düşüşü için tekrar tekrar bildirim gitmesini önlemek için log tablosu
CREATE TABLE IF NOT EXISTS public.bildirim_loglari (
  id bigserial PRIMARY KEY,
  urun_id bigint NOT NULL,
  email text,
  bildirim_tipi text NOT NULL,
  eski_fiyat text,
  yeni_fiyat text,
  yeni_fiyat_num numeric,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 4) Scrape çalışma logları: ileride maliyet, başarı oranı ve sorunlu site takibi için
CREATE TABLE IF NOT EXISTS public.scrape_runs (
  id bigserial PRIMARY KEY,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  total_products integer DEFAULT 0,
  success_count integer DEFAULT 0,
  fail_count integer DEFAULT 0,
  direct_count integer DEFAULT 0,
  proxy_count integer DEFAULT 0,
  render_count integer DEFAULT 0,
  note text
);

-- 5) Performans indeksleri
CREATE INDEX IF NOT EXISTS idx_urunler_satin_alindi ON public.urunler (satin_alindi);
CREATE INDEX IF NOT EXISTS idx_urunler_sonraki_kontrol ON public.urunler (sonraki_kontrol);
CREATE INDEX IF NOT EXISTS idx_urunler_email ON public.urunler (email);
CREATE INDEX IF NOT EXISTS idx_bildirim_loglari_urun_id ON public.bildirim_loglari (urun_id);
CREATE INDEX IF NOT EXISTS idx_bildirim_loglari_created_at ON public.bildirim_loglari (created_at);

-- 6) Mevcut ürünler için ilk kontrol zamanı boşsa şimdiye ayarla
UPDATE public.urunler
SET sonraki_kontrol = now()
WHERE sonraki_kontrol IS NULL;
