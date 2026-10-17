import Link from "next/link";

import { ApprovalBadge, RiskBadge, VerdictBadge } from "@/components/Badge";
import { api, type InventoryItem } from "@/lib/api";

// Always read fresh data. The backend may not even be running at build time.
export const dynamic = "force-dynamic";

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-36 rounded-lg border border-gray-200 px-4 py-3 dark:border-gray-800">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-sm text-gray-500">{label}</div>
    </div>
  );
}

function InventoryTable({ items }: { items: InventoryItem[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-gray-50 text-gray-500 dark:bg-gray-900">
          <tr>
            {["Asset", "Verdict", "Approval", "Risk", "Owner", "Activity", "Region"].map((title) => (
              <th key={title} className="px-3 py-2 font-medium">
                {title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.asset_key} className="border-t border-gray-200 dark:border-gray-800">
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
                {item.owner ? `${item.owner} (${item.owner_source.replaceAll("_", " ")})` : "unknown"}
              </td>
              <td className="px-3 py-2">{item.activity_status.replaceAll("_", " ")}</td>
              <td className="px-3 py-2">{item.region}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function InventoryPage() {
  let items: InventoryItem[];
  try {
    items = await api.inventory();
  } catch {
    return (
      <p className="rounded-lg border border-red-300 p-4 text-sm text-red-700 dark:text-red-300">
        Could not reach the API. Start it with: python -m uvicorn ai_discovery.api.main:app
      </p>
    );
  }

  const shadowCount = items.filter((item) => item.approval_status === "potential_shadow_ai").length;
  const highRiskCount = items.filter((item) => item.risk_tier === "high").length;
  const needsReviewCount = items.filter((item) => item.review_required).length;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">AI inventory</h1>
      <div className="flex flex-wrap gap-3">
        <SummaryCard label="AI assets" value={items.length} />
        <SummaryCard label="Potential shadow AI" value={shadowCount} />
        <SummaryCard label="High risk" value={highRiskCount} />
        <SummaryCard label="Flagged for review" value={needsReviewCount} />
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-gray-500">No AI assets yet. Run a scan first.</p>
      ) : (
        <InventoryTable items={items} />
      )}
    </div>
  );
}