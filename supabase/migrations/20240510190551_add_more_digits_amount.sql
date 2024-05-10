-- Supabase AI is experimental and may produce incorrect answers
-- Always verify the output before executing

alter table public.payments
alter column amount
type numeric(12, 6);