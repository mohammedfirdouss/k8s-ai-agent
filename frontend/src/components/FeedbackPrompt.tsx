"use client";

import { useState } from "react";
import { insforge } from "@/services/insforge";

type Rating = "helpful" | "not_helpful";

type FeedbackPromptProps = {
  investigationId: string;
  // Rating already saved for this investigation, if any.
  initial?: Rating | null;
};

// "Was this diagnosis helpful?" — saved on the user's own history row. The
// database lets users update only the feedback columns of their own rows.
export default function FeedbackPrompt({ investigationId, initial = null }: FeedbackPromptProps) {
  const [rating, setRating] = useState<Rating | null>(initial);
  const [note, setNote] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(next: Rating, feedbackNote: string | null) {
    if (!insforge) return false;
    const { data, error: saveError } = await insforge.database
      .from("investigations")
      .update({ feedback: next, feedback_note: feedbackNote, feedback_at: new Date().toISOString() })
      .eq("id", investigationId)
      .select("id");
    // Row-level security turns an update of someone else's (or a missing) row
    // into "0 rows updated", not an error, so check a row actually changed.
    if (saveError || !data?.length) {
      setError("Could not save your feedback.");
      return false;
    }
    setError(null);
    return true;
  }

  async function rate(next: Rating) {
    if (await save(next, null)) {
      setRating(next);
      setNoteSaved(false);
    }
  }

  async function sendNote(event: React.FormEvent) {
    event.preventDefault();
    if (rating && note.trim() && (await save(rating, note.trim()))) setNoteSaved(true);
  }

  const button = (value: Rating, label: string) => (
    <button
      type="button"
      onClick={() => rate(value)}
      aria-pressed={rating === value}
      className={
        rating === value
          ? "rounded-md border border-slate-900 bg-slate-900 px-3 py-1 text-xs text-white"
          : "rounded-md border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100"
      }
    >
      {label}
    </button>
  );

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-5 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-slate-700">
          {rating ? "Thanks for the feedback." : "Was this diagnosis helpful?"}
        </span>
        {button("helpful", "👍 Yes")}
        {button("not_helpful", "👎 No")}
      </div>
      {rating === "not_helpful" && !noteSaved && (
        <form onSubmit={sendNote} className="mt-3 flex gap-2">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={2000}
            placeholder="What was wrong or missing? (optional)"
            className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-900 focus:outline-none"
          />
          <button type="submit" className="rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100">
            Send
          </button>
        </form>
      )}
      {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
    </div>
  );
}
