"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApprovalBadge, RiskBadge, VerdictBadge } from "@/components/Badge";
import { api, type QueueItem, type ReviewDecision } from "@/lib/api";

type Draft = { assetKey: string; decision: ReviewDecision };

export default function ReviewQueue({ items }: { items: QueueItem[] }) {
  const router = useRouter();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function open(assetKey: string, decision: ReviewDecision) {
    setDraft({ assetKey, decision });
    setError(null);
  }

  async function submit() {
    if (!draft) return;
    if (!reviewer.trim() || !reason.trim()) {
      setError("Reviewer and reason are both required.");
      return;
    }
    setSaving(true);
    try {
      await api.submitReview({
        asset_key: draft.assetKey,
        decision: draft.decision,
        reviewer: reviewer.trim(),
        reason: reason.trim(),
      });
      setDraft(null);
      setReason("");
      router.refresh(); // re-fetch the queue on the server
    } catch {
      setError("Could not save the review. Is the API running?");
    } finally {
      setSaving(false);
    }
  }

  if (items.length === 0) {
    return <p className="text-sm text-gray-500">Nothing is waiting for review.</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Reviewer names are self-declared. The API has no login yet.
      </p>
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-gray-500 dark:bg-gray-900">
            <tr>
              {["Asset", "Verdict", "Approval", "Risk", "Status", "Why", ""].map((title) => (
                <th key={title} className="px-3 py-2 font-medium">
                  {title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.asset_key} className="border-t border-gray-200 align-top dark:border-gray-800">
                <td className="px-3 py-2">
                  <Link
                    href={`/asset?key=${encodeURIComponent(item.asset_key)}`}
                    className="text-blue-600 hover:underline dark:text-blue-400"
                  >
                    {item.name}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <VerdictBadge value={item.ai_verdict} />
                </td>
                <td className="px-3 py-2">
                  <ApprovalBadge value={item.approval_status} />
                </td>
                <td className="px-3 py-2">
                  <RiskBadge value={item.risk_tier} />
                </td>
                <td className="px-3 py-2">
                  {item.review_status.replaceAll("_", " ")}
                  {item.last_reviewer && (
                    <div className="text-xs text-gray-500">
                      {item.last_reviewer}: {item.last_reason}
                    </div>
                  )}
                </td>
                <td className="max-w-xs px-3 py-2 text-gray-600 dark:text-gray-400">{item.reasoning}</td>
                <td className="whitespace-nowrap px-3 py-2">
                  <button
                    onClick={() => open(item.asset_key, "approve")}
                    className="mr-2 rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => open(item.asset_key, "escalate")}
                    className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
                  >
                    Escalate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {draft && (
        <div className="space-y-3 rounded-lg border border-gray-300 p-4 dark:border-gray-700">
          <div className="text-sm font-medium">
            {draft.decision === "approve" ? "Approve" : "Escalate"}:{" "}
            <span className="break-all font-normal">{draft.assetKey}</span>
          </div>
          <input
            value={reviewer}
            onChange={(event) => setReviewer(event.target.value)}
            placeholder="Your name"
            className="block w-full max-w-sm rounded border border-gray-300 bg-transparent px-2 py-1 text-sm dark:border-gray-700"
          />
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Reason for this decision"
            rows={3}
            className="block w-full max-w-xl rounded border border-gray-300 bg-transparent px-2 py-1 text-sm dark:border-gray-700"
          />
          {error && <p className="text-sm text-red-700 dark:text-red-300">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={submit}
              disabled={saving}
              className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save decision"}
            </button>
            <button onClick={() => setDraft(null)} className="rounded border px-3 py-1 text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}