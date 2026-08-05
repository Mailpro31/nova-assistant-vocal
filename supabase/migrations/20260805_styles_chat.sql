-- Reformulation cloud (Styles) — 2026-08-05
-- Compteur quotidien par machine pour la fonction edge « styles-chat »
-- (reformulation via Anthropic côté serveur, Pro/Ultra). Même pattern que
-- turbo_consume_capped : contrôle + incrément atomiques (verrou de ligne),
-- remboursement possible via delta négatif.

create table if not exists public.styles_usage (
  machine_hash text not null,
  day date not null,
  count int not null default 0,
  primary key (machine_hash, day)
);

create or replace function public.styles_consume_capped(
  p_machine text, p_count int, p_cap int
) returns boolean
language plpgsql security definer as $$
begin
  insert into public.styles_usage (machine_hash, day, count)
  values (p_machine, current_date, 0)
  on conflict (machine_hash, day) do nothing;

  update public.styles_usage
  set count = count + p_count
  where machine_hash = p_machine
    and day = current_date
    and count + p_count <= p_cap;
  return found;
end;
$$;

-- Remboursement (delta négatif, plancher à 0) quand le fournisseur échoue.
create or replace function public.styles_consume(p_machine text, p_count int)
returns void
language plpgsql security definer as $$
begin
  insert into public.styles_usage (machine_hash, day, count)
  values (p_machine, current_date, p_count)
  on conflict (machine_hash, day)
  do update set count = greatest(0, public.styles_usage.count + p_count);
end;
$$;
