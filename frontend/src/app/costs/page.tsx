import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const usd = (value: number) => `$${value.toFixed(5)}`;

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-36 rounded-lg border border-gray-200 px-4 py-3 dark:border-gray-800">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-sm text-gray-500">{label}</div>
    </div>
  );
}

export default async function CostsPage() {
  let report;
  try {
    report = await api.llmCost();
  } catch {
    return <p className="text-sm text-red-700 dark:text-red-300">Could not reach the API.</p>;
  }
  if (!report) return <p className="text-sm text-gray-500">No scans yet. Run a scan first.</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">LLM routing and cost</h1>
      {!report.llm_used ? (
        <p className="text-sm text-gray-500">
          The latest scan did not use the LLM, so the rules alone made every decision. Run a scan
          without --no-llm to see routing numbers.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-3">
            <Stat label="model calls" value={report.total_calls} />
            <Stat label="small tier" value={report.calls_by_tier.small ?? 0} />
            <Stat label="large tier" value={report.calls_by_tier.large ?? 0} />
            <Stat label="escalated" value={report.escalated_calls} />
            <Stat label="actual cost" value={usd(report.total_cost_usd)} />
            <Stat label="if all large (est.)" value={usd(report.all_large_cost_usd)} />
          </div>
          <p className="text-sm text-gray-500">
            Small: {report.small_model}. Large: {report.large_model}. {report.note}
          </p>
          <p className="text-sm">
            Outcomes:{" "}
            {Object.entries(report.outcomes)
              .map(([name, count]) => `${name.replaceAll("_", " ")} ${count}`)
              .join(", ")}
          </p>
        </>
      )}
    </div>
  );
}