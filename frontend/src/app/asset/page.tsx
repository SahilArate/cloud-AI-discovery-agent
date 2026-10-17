import Link from "next/link";

import { ApprovalBadge, RiskBadge, VerdictBadge } from "@/components/Badge";
import { api, type ObservationItem } from "@/lib/api";

export const dynamic = "force-dynamic";

const pretty = (value: string) => value.replaceAll("_", " ");
const when = (iso: string) => new Date(iso).toLocaleString();

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-0.5 text-sm">{children}</div>
    </div>
  );
}

function usageText(obs: ObservationItem) {
  if (obs.usage_count === null) return pretty(obs.activity_status);
  return `${obs.usage_count} calls in ${obs.usage_window_days} days (${pretty(obs.activity_status)})`;
}

function EvidenceTable({ obs }: { obs: ObservationItem }) {
  if (obs.evidence.length === 0) {
    return <p className="text-sm text-gray-500">No evidence records for this observation.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-gray-500">
        <tr>
          {["Type", "Strength", "Source", "Detail"].map((title) => (
            <th key={title} className="py-1 pr-3 font-medium">
              {title}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {obs.evidence.map((item) => (
          <tr key={item.evidence_id} className="border-t border-gray-200 dark:border-gray-800">
            <td className="py-1 pr-3">{pretty(item.evidence_type)}</td>
            <td className="py-1 pr-3">{item.strength}</td>
            <td className="py-1 pr-3">{item.source}</td>
            <td className="py-1 pr-3">{item.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function AssetPage({
  searchParams,
}: {
  searchParams: Promise<{ key?: string }>;
}) {
  const { key } = await searchParams;
  if (!key) return <p className="text-sm text-gray-500">No asset selected.</p>;

  let asset, reviews;
  try {
    [asset, reviews] = await Promise.all([api.asset(key), api.reviewHistory(key)]);
  } catch {
    return <p className="text-sm text-red-700 dark:text-red-300">Could not reach the API.</p>;
  }
  if (!asset) return <p className="text-sm text-gray-500">Asset not found.</p>;

  const latest = asset.observations[0];

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-blue-600 hover:underline dark:text-blue-400">
        &larr; Back to inventory
      </Link>

      <div>
        <h1 className="text-xl font-semibold">{asset.name}</h1>
        <p className="break-all text-xs text-gray-500">{asset.native_id}</p>
      </div>

      {latest && (
        <section className="space-y-4 rounded-lg border border-gray-200 p-4 dark:border-gray-800">
          <div className="flex flex-wrap gap-2">
            <VerdictBadge value={latest.ai_verdict} />
            <ApprovalBadge value={latest.approval_status} />
            <RiskBadge value={latest.risk_tier} />
            {latest.review_required && (
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs dark:bg-gray-800">
                review required
              </span>
            )}
          </div>
          <p className="text-sm">{latest.reasoning}</p>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Provider">{asset.provider}</Field>
            <Field label="Account">{asset.account_id}</Field>
            <Field label="Owner">
              {latest.owner ? `${latest.owner} (${pretty(latest.owner_source)})` : "unknown"}
            </Field>
            <Field label="Usage">{usageText(latest)}</Field>
            <Field label="Decided by">{pretty(latest.decided_by)}</Field>
            <Field label="First seen">{when(asset.first_seen)}</Field>
          </div>
          {latest.missing_evidence.length > 0 && (
            <Field label="Would settle it">{latest.missing_evidence.map(pretty).join(", ")}</Field>
          )}
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-gray-500">Evidence</div>
            <EvidenceTable obs={latest} />
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 font-semibold">Observation history</h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 text-gray-500 dark:bg-gray-900">
              <tr>
                {["Observed", "Verdict", "Approval", "Risk", "Decided by"].map((title) => (
                  <th key={title} className="px-3 py-2 font-medium">
                    {title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {asset.observations.map((obs) => (
                <tr
                  key={obs.observation_id}
                  className="border-t border-gray-200 dark:border-gray-800"
                >
                  <td className="px-3 py-2">{when(obs.observed_at)}</td>
                  <td className="px-3 py-2">
                    <VerdictBadge value={obs.ai_verdict} />
                  </td>
                  <td className="px-3 py-2">
                    <ApprovalBadge value={obs.approval_status} />
                  </td>
                  <td className="px-3 py-2">
                    <RiskBadge value={obs.risk_tier} />
                  </td>
                  <td className="px-3 py-2">{pretty(obs.decided_by)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Review decisions</h2>
        {reviews.length === 0 ? (
          <p className="text-sm text-gray-500">No one has reviewed this asset yet.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {reviews.map((review) => (
              <li
                key={review.review_id}
                className="rounded-lg border border-gray-200 p-3 dark:border-gray-800"
              >
                <span className="font-medium">{review.status}</span> by {review.reviewer} on{" "}
                {when(review.created_at)}
                <div className="text-gray-600 dark:text-gray-400">{review.reason}</div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}