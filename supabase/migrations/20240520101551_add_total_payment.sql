ALTER TABLE public.payments
ADD COLUMN total_payment INT,
ADD COLUMN additional_info json;