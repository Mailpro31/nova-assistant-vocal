-- Quota Turbo FREE « 20 à vie » — 2026-08-11
-- Compteur CUMULATIF par machine (jamais remis à zéro) pour la fonction edge
-- « styles-chat » quand l'app envoie un jeton NOVAFREE.<empreinte>.
-- Même pattern que turbo_consume_capped : contrôle + incrément atomiques
-- (verrou de ligne), remboursement via delta négatif.

create table if not exists public.styles_free_usage (
  machine_hash text primary key,
  count int not null default 0
);

-- Consommation plafonnée À VIE : true si le crédit a été pris, false si le
-- plafond à vie est déjà atteint.
create or replace function public.styles_free_consume_capped(
  p_machine text, p_cap int
) returns boolean
language plpgsql security definer as $$
begin
  insert into public.styles_free_usage (machine_hash, count)
  values (p_machine, 0)
  on conflict (machine_hash) do nothing;

  update public.styles_free_usage
  set count = count + 1
  where machine_hash = p_machine
    and count + 1 <= p_cap;
  return found;
end;
$$;

-- Remboursement (delta négatif, plancher à 0) quand le fournisseur échoue,
-- et consommation directe (delta positif) pour le repli legacy.
create or replace function public.styles_free_consume(p_machine text, p_count int)
returns void
language plpgsql security definer as $$
begin
  insert into public.styles_free_usage (machine_hash, count)
  values (p_machine, p_count)
  on conflict (machine_hash)
  do update set count = greatest(0, public.styles_free_usage.count + p_count);
end;
$$;
