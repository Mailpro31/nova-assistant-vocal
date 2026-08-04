-- Audit sécurité 2026-08-04 — migrations à appliquer dans le dashboard
-- Supabase (SQL Editor) AVANT de redéployer les edge functions.
--
-- 1) trial-check : colonne d'empreinte réseau (IP hachée, pseudonyme) pour
--    borner le nombre de nouvelles empreintes machine scellées par réseau
--    et par jour (anti reset d'essai industrialisé).
alter table public.trial_starts
  add column if not exists iph text;

create index if not exists trial_starts_iph_day_idx
  on public.trial_starts (iph, started_on);

-- 2) turbo / turbo-vision : consommation de quota ATOMIQUE plafonnée.
--    La vérification « used + delta <= cap » et l'incrément se font dans la
--    même transaction (verrou de ligne), ce qui ferme la course concurrente
--    où N requêtes simultanées lisaient toutes le même compteur et passaient
--    toutes le contrôle. Les fonctions edge consomment AVANT l'appel Groq et
--    remboursent (delta négatif) si le fournisseur échoue.
--
--    ⚠️ Vérifiez le type de la colonne `day` : si c'est du texte, remplacez
--    `current_date` par `current_date::text` ci-dessous.

create or replace function public.turbo_consume_capped(
  p_machine text, p_seconds int, p_cap int
) returns boolean
language plpgsql security definer as $$
begin
  insert into public.turbo_usage (machine_hash, day, seconds)
  values (p_machine, current_date, 0)
  on conflict (machine_hash, day) do nothing;

  update public.turbo_usage
  set seconds = seconds + p_seconds
  where machine_hash = p_machine
    and day = current_date
    and seconds + p_seconds <= p_cap;
  return found;
end;
$$;

create or replace function public.turbo_vision_consume_capped(
  p_machine text, p_images int, p_cap int
) returns boolean
language plpgsql security definer as $$
begin
  insert into public.turbo_vision_usage (machine_hash, day, images)
  values (p_machine, current_date, 0)
  on conflict (machine_hash, day) do nothing;

  update public.turbo_vision_usage
  set images = images + p_images
  where machine_hash = p_machine
    and day = current_date
    and images + p_images <= p_cap;
  return found;
end;
$$;

-- 3) Remboursement : les RPC historiques acceptent désormais un delta
--    NÉGATIF (plancher à 0) pour annuler la consommation d'un appel fournisseur
--    en échec. Le comportement pour les deltas positifs est inchangé.
create or replace function public.turbo_consume(p_machine text, p_seconds int)
returns void
language plpgsql security definer as $$
begin
  insert into public.turbo_usage (machine_hash, day, seconds)
  values (p_machine, current_date, p_seconds)
  on conflict (machine_hash, day)
  do update set seconds = greatest(0, public.turbo_usage.seconds + p_seconds);
end;
$$;

create or replace function public.turbo_vision_consume(p_machine text, p_images int)
returns void
language plpgsql security definer as $$
begin
  insert into public.turbo_vision_usage (machine_hash, day, images)
  values (p_machine, current_date, p_images)
  on conflict (machine_hash, day)
  do update set images = greatest(0, public.turbo_vision_usage.images + p_images);
end;
$$;
