-- Let users rate their own diagnoses (helpful / not helpful, optional note).
--
-- Users may update ONLY the feedback columns, and only on their own rows:
-- the column-level grant blocks every other column (root cause, diagnosis,
-- owner), and the policy limits updates to rows they own.

ALTER TABLE public.investigations
  ADD COLUMN feedback text CHECK (feedback IN ('helpful', 'not_helpful')),
  ADD COLUMN feedback_note text CHECK (char_length(feedback_note) <= 2000),
  ADD COLUMN feedback_at timestamptz;

GRANT UPDATE (feedback, feedback_note, feedback_at) ON public.investigations TO authenticated;

CREATE POLICY investigations_feedback_own
ON public.investigations FOR UPDATE
TO authenticated
USING (user_id = (SELECT auth.uid()))
WITH CHECK (user_id = (SELECT auth.uid()));
