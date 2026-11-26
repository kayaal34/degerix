-- KVKK 11. madde haklarının çalışan hâli.
--
-- Aydınlatma metni yazmak kolaydır; asıl iş, metinde söz verilen hakkın
-- gerçekten yerine getirilebilmesidir. İki hak kod gerektiriyor:
--
--   * Erişim ve taşınabilirlik: kullanıcı kendi verisinin tamamını indirebilmeli.
--   * Silme (unutulma): kullanıcı hesabını ve bütün kayıtlarını silebilmeli.
--
-- İkisi de kullanıcının kendi oturum jetonuyla çalışır; sunucuda bütün
-- kullanıcıların verisini açan bir anahtar yine yok.

-- ─────────────────────── Erişim: verimin tamamı ───────────────────────

create or replace function public.degerix_verilerim()
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_user uuid := auth.uid();
  v_kullanici jsonb;
begin
  if v_user is null then
    return jsonb_build_object('hata', 'oturum_yok');
  end if;

  select jsonb_build_object(
           'kimlik', u.id, 'eposta', u.email, 'telefon', u.phone,
           'kayit_tarihi', u.created_at, 'son_giris', u.last_sign_in_at)
    into v_kullanici
    from auth.users u where u.id = v_user;

  return jsonb_build_object(
    'uretildi', now(),
    'aciklama', 'KVKK 11. madde kapsamında, Değerix''in sizin hakkınızda tuttuğu verinin tamamı.',
    'hesap', v_kullanici,
    'profil', (select to_jsonb(p) from public.degerix_profiles p where p.id = v_user),
    'abonelikler', coalesce((select jsonb_agg(to_jsonb(s) order by s.created_at)
                               from public.degerix_subscriptions s where s.user_id = v_user), '[]'::jsonb),
    'sorgular', coalesce((select jsonb_agg(to_jsonb(q) order by q.created_at)
                            from public.degerix_queries q where q.user_id = v_user), '[]'::jsonb)
  );
end;
$$;

-- ─────────────────────── Silme: hesabın tamamı ───────────────────────

create or replace function public.degerix_hesabimi_sil()
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_user uuid := auth.uid();
  v_sorgu integer;
begin
  if v_user is null then
    return jsonb_build_object('silindi', false, 'sebep', 'oturum_yok');
  end if;

  select count(*) into v_sorgu from public.degerix_queries where user_id = v_user;

  -- auth.users silinince profil, abonelik ve sorgular yabancı anahtar
  -- zinciriyle birlikte gider; geride tek satır kalmaz. Silme geri alınamaz.
  delete from auth.users where id = v_user;

  return jsonb_build_object('silindi', true, 'silinen_sorgu', v_sorgu);
end;
$$;

grant execute on function public.degerix_verilerim()     to authenticated;
grant execute on function public.degerix_hesabimi_sil()  to authenticated;

-- Kullanıcı kendi sorgu geçmişini tek tek de silebilmeli: geçmişini
-- temizlemek için hesabını kapatmak zorunda kalmasın.
create or replace function public.degerix_gecmisimi_sil()
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_user uuid := auth.uid();
  v_silinen integer;
begin
  if v_user is null then
    return jsonb_build_object('silindi', false, 'sebep', 'oturum_yok');
  end if;
  -- Ücretsiz hak sayımı bu tabloya bakıyor; geçmişi silmek hakkı geri
  -- getirmemeli, yoksa kota tek düğmeyle sıfırlanır. Bu yüzden kayıtlar
  -- silinmiyor, künyesi temizleniyor: ne sorulduğu gidiyor, sayı kalıyor.
  update public.degerix_queries
     set province = null, district = null, lat = null, lng = null,
         area_m2 = null, usage = null, parcel = null,
         unit_price = null, total = null
   where user_id = v_user and province is not null;
  get diagnostics v_silinen = row_count;
  return jsonb_build_object('silindi', true, 'temizlenen', v_silinen);
end;
$$;

grant execute on function public.degerix_gecmisimi_sil() to authenticated;
