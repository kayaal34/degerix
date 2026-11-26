-- Değerix abonelik altyapısı — Supabase (Postgres) şeması.
--
-- Kurulum: Supabase panelinde SQL Editor'e yapıştırıp çalıştırmak yeterli.
--
-- Tasarımın iki kuralı var:
--   1. Kota istemcide tutulmaz. Sorgu hakkı yalnızca aşağıdaki security definer
--      fonksiyonlarla açılır; istemci degerix_queries tablosuna doğrudan satır
--      ekleyemez, dolayısıyla kendi kendine hak yazamaz.
--   2. Sunucunun service_role anahtarına ihtiyacı yoktur. Uygulama kullanıcının
--      kendi oturum jetonunu taşır, satır güvenliği ve auth.uid() işi yapar.
--      Böylece sızdığında her şeyi açan bir anahtar hiç var olmaz.

-- ─────────────────────────── Tablolar ───────────────────────────

create table if not exists public.degerix_profiles (
  id          uuid primary key references auth.users on delete cascade,
  phone       text,
  full_name   text,
  free_quota  integer not null default 3,   -- ilk üç sorgu ücretsiz
  created_at  timestamptz not null default now()
);

create table if not exists public.degerix_subscriptions (
  id           bigint generated always as identity primary key,
  user_id      uuid not null references auth.users on delete cascade,
  plan         text not null,                   -- 'aylik' | 'yillik' | 'paket'
  status       text not null default 'active',  -- 'active' | 'past_due' | 'canceled'
  allowance    integer,                         -- null = sınırsız sorgu
  started_at   timestamptz not null default now(),
  expires_at   timestamptz,
  provider     text,                            -- ödeme sağlayıcısı
  provider_ref text,
  created_at   timestamptz not null default now()
);
create index if not exists degerix_subscriptions_user_idx
  on public.degerix_subscriptions (user_id, status);

create table if not exists public.degerix_queries (
  id              bigint generated always as identity primary key,
  user_id         uuid not null references auth.users on delete cascade,
  created_at      timestamptz not null default now(),
  province        text,
  district        text,
  lat             double precision,
  lng             double precision,
  area_m2         numeric,
  usage           text,
  parcel          text,
  unit_price      numeric,
  total           numeric,
  source          text not null default 'free',  -- 'free' | 'subscription'
  subscription_id bigint references public.degerix_subscriptions on delete set null
);
create index if not exists degerix_queries_user_idx
  on public.degerix_queries (user_id, created_at desc);

-- ─────────────────────── Kayıt olanın profili ───────────────────────

create or replace function public.degerix_profil_ac()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  insert into public.degerix_profiles (id, phone)
  values (new.id, new.phone)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists degerix_profil_ac_trg on auth.users;
create trigger degerix_profil_ac_trg
  after insert on auth.users
  for each row execute function public.degerix_profil_ac();

-- ─────────────────────────── Hak durumu ───────────────────────────

create or replace function public.degerix_hak_durumu()
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_user       uuid := auth.uid();
  v_free       integer;
  v_used_free  integer;
  v_sub        public.degerix_subscriptions%rowtype;
  v_sub_used   integer := 0;
  v_sub_kalan  integer;
begin
  if v_user is null then
    return jsonb_build_object('oturum', false);
  end if;

  select free_quota into v_free from public.degerix_profiles where id = v_user;
  v_free := coalesce(v_free, 3);
  select count(*) into v_used_free
    from public.degerix_queries where user_id = v_user and source = 'free';

  select * into v_sub from public.degerix_subscriptions
    where user_id = v_user and status = 'active'
      and (expires_at is null or expires_at > now())
    order by expires_at desc nulls first
    limit 1;

  if v_sub.id is not null and v_sub.allowance is not null then
    select count(*) into v_sub_used
      from public.degerix_queries where subscription_id = v_sub.id;
    v_sub_kalan := greatest(v_sub.allowance - v_sub_used, 0);
  end if;

  return jsonb_build_object(
    'oturum', true,
    'ucretsiz_hak', v_free,
    'ucretsiz_kalan', greatest(v_free - v_used_free, 0),
    'abonelik', case when v_sub.id is null then null else jsonb_build_object(
        'plan', v_sub.plan,
        'bitis', v_sub.expires_at,
        'hak', v_sub.allowance,
        'kalan', v_sub_kalan) end,
    'sorgu_hakki_var',
      (v_free - v_used_free) > 0
      or (v_sub.id is not null and (v_sub.allowance is null or v_sub_kalan > 0))
  );
end;
$$;

-- ─────────────────────────── Sorgu açma ───────────────────────────
-- Değerleme hesaplanmadan ÖNCE çağrılır: hakkı atomik olarak kontrol eder ve
-- kaydı açar. Hesap bittiğinde degerix_sorgu_sonuc ile sonuç yazılır, hesap
-- patlarsa degerix_sorgu_iptal ile hak geri verilir.

create or replace function public.degerix_sorgu_ac(
  p_province text default null,
  p_district text default null,
  p_lat      double precision default null,
  p_lng      double precision default null,
  p_area     numeric default null,
  p_usage    text default null,
  p_parcel   text default null)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_user      uuid := auth.uid();
  v_durum     jsonb;
  v_sub       public.degerix_subscriptions%rowtype;
  v_kaynak    text;
  v_id        bigint;
begin
  if v_user is null then
    return jsonb_build_object('izin', false, 'sebep', 'oturum_yok');
  end if;

  v_durum := public.degerix_hak_durumu();

  if (v_durum->>'ucretsiz_kalan')::int > 0 then
    v_kaynak := 'free';
  elsif (v_durum->>'sorgu_hakki_var')::boolean then
    v_kaynak := 'subscription';
    select * into v_sub from public.degerix_subscriptions
      where user_id = v_user and status = 'active'
        and (expires_at is null or expires_at > now())
      order by expires_at desc nulls first
      limit 1;
  else
    return jsonb_build_object('izin', false, 'sebep', 'hak_bitti', 'durum', v_durum);
  end if;

  insert into public.degerix_queries
    (user_id, province, district, lat, lng, area_m2, usage, parcel, source, subscription_id)
  values
    (v_user, p_province, p_district, p_lat, p_lng, p_area, p_usage, p_parcel, v_kaynak, v_sub.id)
  returning id into v_id;

  return jsonb_build_object(
    'izin', true, 'sorgu_id', v_id, 'kaynak', v_kaynak,
    'durum', public.degerix_hak_durumu());
end;
$$;

create or replace function public.degerix_sorgu_sonuc(
  p_id bigint, p_unit_price numeric, p_total numeric)
returns void
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  update public.degerix_queries
     set unit_price = p_unit_price, total = p_total
   where id = p_id and user_id = auth.uid();
end;
$$;

create or replace function public.degerix_sorgu_iptal(p_id bigint)
returns void
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  -- Değerleme tamamlanamadıysa hak yanmaz.
  delete from public.degerix_queries
   where id = p_id and user_id = auth.uid() and unit_price is null;
end;
$$;

-- ───────────────────── Satır güvenliği ─────────────────────
-- Okuma kendi satırlarıyla sınırlı; yazma yolu yalnızca yukarıdaki
-- fonksiyonlar. Tabloya doğrudan insert/update/delete politikası YOKTUR,
-- bu yüzden istemci kendi kotasını yazamaz.

alter table public.degerix_profiles      enable row level security;
alter table public.degerix_subscriptions enable row level security;
alter table public.degerix_queries       enable row level security;

drop policy if exists degerix_profiles_self on public.degerix_profiles;
create policy degerix_profiles_self on public.degerix_profiles
  for select using (auth.uid() = id);

drop policy if exists degerix_profiles_update_self on public.degerix_profiles;
create policy degerix_profiles_update_self on public.degerix_profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists degerix_subscriptions_self on public.degerix_subscriptions;
create policy degerix_subscriptions_self on public.degerix_subscriptions
  for select using (auth.uid() = user_id);

drop policy if exists degerix_queries_self on public.degerix_queries;
create policy degerix_queries_self on public.degerix_queries
  for select using (auth.uid() = user_id);

grant execute on function public.degerix_hak_durumu()  to authenticated;
grant execute on function public.degerix_sorgu_ac(text, text, double precision, double precision, numeric, text, text) to authenticated;
grant execute on function public.degerix_sorgu_sonuc(bigint, numeric, numeric) to authenticated;
grant execute on function public.degerix_sorgu_iptal(bigint) to authenticated;
