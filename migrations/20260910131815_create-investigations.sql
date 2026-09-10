-- Investigation history for the AI Kubernetes Troubleshooting Agent.

CREATE TABLE public.investigations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  root_cause text,
  namespace text,
  confidence numeric,
  status text
);

-- Any signed-in user can read and add history rows; no updates/deletes.
ALTER TABLE public.investigations ENABLE ROW LEVEL SECURITY;

CREATE POLICY investigations_select
ON public.investigations FOR SELECT
TO authenticated
USING (true);

CREATE POLICY investigations_insert
ON public.investigations FOR INSERT
TO authenticated
WITH CHECK (true);

-- Realtime: allow subscribing to the 'investigations' channel and publish
-- an INSERT event whenever a new investigation row is saved.
INSERT INTO realtime.channels (pattern, description, enabled)
VALUES ('investigations', 'New investigation history rows', true)
ON CONFLICT (pattern) DO UPDATE
SET description = EXCLUDED.description,
    enabled = EXCLUDED.enabled;

CREATE OR REPLACE FUNCTION public.notify_investigation_insert()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM realtime.publish(
    'investigations',
    'INSERT',
    jsonb_build_object(
      'id', NEW.id,
      'created_at', NEW.created_at,
      'root_cause', NEW.root_cause,
      'namespace', NEW.namespace,
      'confidence', NEW.confidence,
      'status', NEW.status
    )
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER investigations_insert_trigger
AFTER INSERT ON public.investigations
FOR EACH ROW
EXECUTE FUNCTION public.notify_investigation_insert();
