-- Rafta scalable price tracking foundation
-- Safe/idempotent migration for Supabase PostgreSQL.

-- 1) Product tracking runtime columns
alter table if exists public.urunler
  add column if not exists son_kontrol timestamptz,
  add column if not exists sonraki_kontrol timestamptz,
  add column if not exists son_basarili_kontrol timestamptz,
  add column if not exists hata_sayisi integer not null default 0,
  add column if not exists son_hata text,
  add column if not exists scrape_yontemi text,
  add column if not exists son_fiyat_num numeric(12,2),
  add column if not exists ilk_fiyat_num numeric(12,2),
  add column if not exists son_bildirim_fiyat_num numeric(12,2),
  add column if not exists son_bildirim_at timestamptz;

-- 2) Price history numeric column for reliable comparisons/charts
alter table if exists public.fiyat_gecmisi
  add column if not exists fiyat_num numeric(12,2),
  add column if not exists scrape_yontemi text;

-- 3) Notification log: prevents duplicate notifications for the same event
create table if not exists public.bildirim_loglari (
  id bigserial primary key,
  urun_id bigint not null,
  email text,
  bildirim_tipi text not null,
  fiyat text,
  fiyat_num numeric(12,2),
  kanal text default 'email_push',
  created_at timestamptz not null default now()
);

-- 4) Scrape run metrics: useful later for cost/success analysis
create table if not exists public.scrape_runs (
  id bigserial primary key,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  checked_count integer not null default 0,
  success_count integer not null default 0,
  failed_count integer not null default 0,
  direct_count integer not null default 0,
  proxy_count integer not null default 0,
  render_count integer not null default 0,
  notes text
);

-- 5) Indexes. Dynamic blocks avoid failures if an older schema differs.
do $$
begin
  if to_regclass('public.urunler') is not null then
    create index if not exists idx_urunler_sonraki_kontrol
      on public.urunler (sonraki_kontrol);

    create index if not exists idx_urunler_hata_sayisi
      on public.urunler (hata_sayisi);

    if exists (
      select 1 from information_schema.columns
      where table_schema = 'public' and table_name = 'urunler' and column_name = 'email'
    ) then
      create index if not exists idx_urunler_email
        on public.urunler (email);
    end if;

    if exists (
      select 1 from information_schema.columns
      where table_schema = 'public' and table_name = 'urunler' and column_name = 'satin_alindi'
    ) then
      create index if not exists idx_urunler_active_schedule
        on public.urunler (satin_alindi, sonraki_kontrol, id);
    end if;

    if exists (
      select 1 from information_schema.columns
      where table_schema = 'public' and table_name = 'urunler' and column_name = 'guncelleme_istegi'
    ) then
      create index if not exists idx_urunler_manual_update
        on public.urunler (guncelleme_istegi, id);
    end if;
  end if;

  if to_regclass('public.fiyat_gecmisi') is not null then
    create index if not exists idx_fiyat_gecmisi_urun_id
      on public.fiyat_gecmisi (urun_id);
  end if;
end $$;

create index if not exists idx_bildirim_loglari_urun_id
  on public.bildirim_loglari (urun_id);

create index if not exists idx_bildirim_loglari_created_at
  on public.bildirim_loglari (created_at desc);

create unique index if not exists uq_bildirim_loglari_event_numeric
  on public.bildirim_loglari (urun_id, bildirim_tipi, fiyat_num)
  where fiyat_num is not null;

create unique index if not exists uq_bildirim_loglari_event_text
  on public.bildirim_loglari (urun_id, bildirim_tipi, fiyat)
  where fiyat_num is null and fiyat is not null;

-- 6) Optional RLS enablement for new tables.
-- These tables are used by backend cron/service key. Policies can be tightened later.
alter table public.bildirim_loglari enable row level security;
alter table public.scrape_runs enable row level security;
