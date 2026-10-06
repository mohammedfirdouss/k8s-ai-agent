-- Scope investigation history to its owner.
--
-- Before: any signed-in user could read every row and insert arbitrary rows
-- from the browser. After: rows carry the owning user's id, users can only
-- read their own rows, and only the backend (admin API key) writes them.

ALTER TABLE public.investigations
  ADD COLUMN user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  ADD COLUMN cluster_context text,
  ADD COLUMN diagnosis jsonb;

-- Rows written before this migration have no owner; with the policy below
-- they become invisible to everyone (nothing is deleted).

CREATE INDEX investigations_user_created_idx
  ON public.investigations (user_id, created_at DESC);

DROP POLICY IF EXISTS investigations_select ON public.investigations;
DROP POLICY IF EXISTS investigations_insert ON public.investigations;

CREATE POLICY investigations_select_own
ON public.investigations FOR SELECT
TO authenticated
USING (user_id = (SELECT auth.uid()));

-- History is written server-side only; clients get read access.
REVOKE INSERT, UPDATE, DELETE ON public.investigations FROM anon, authenticated;
GRANT SELECT ON public.investigations TO authenticated;

-- Realtime: replace the shared 'investigations' channel (which broadcast
-- every user's root causes to every subscriber) with per-user channels
-- named 'investigations:<user_id>'.
UPDATE realtime.channels SET enabled = false WHERE pattern = 'investigations';

INSERT INTO realtime.channels (pattern, description, enabled)
VALUES ('investigations:%', 'New investigation history rows, per user', true)
ON CONFLICT (pattern) DO UPDATE
SET description = EXCLUDED.description,
    enabled = EXCLUDED.enabled;

ALTER TABLE realtime.channels ENABLE ROW LEVEL SECURITY;

CREATE POLICY investigations_subscribe_own
ON realtime.channels FOR SELECT
TO authenticated
USING (
  pattern = 'investigations:%'
  AND realtime.channel_name() = 'investigations:' || (SELECT auth.uid())::text
);

CREATE OR REPLACE FUNCTION public.notify_investigation_insert()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.user_id IS NULL THEN
    RETURN NEW;
  END IF;
  PERFORM realtime.publish(
    'investigations:' || NEW.user_id::text,
    'INSERT',
    jsonb_build_object(
      'id', NEW.id,
      'created_at', NEW.created_at,
      'root_cause', NEW.root_cause,
      'cluster_context', NEW.cluster_context,
      'confidence', NEW.confidence,
      'status', NEW.status
    )
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
