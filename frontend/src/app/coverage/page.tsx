import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, string> = {
  complete: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  partial: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

export default async function CoveragePage() {
  let report;
  try {
    report = await api.coverage();
  } catch {
    return <p className="text-sm text-red-700 dark:text-red-300">Could not reach the API.</p>;
  }
  if (!report) return <p className="text-sm text-gray-500">No scans yet. Run a scan first.</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Coverage</h1>
      <p className="text-sm text-gray-500">
        What the latest scan could and could not inspect. A scan that found few AI assets is only
        trustworthy if the scopes it looked at were fully inspected.
      </p>
      <div className="flex flex-wrap gap-3">
        <div className="min-w-36 rounded-lg border border-gray-200 px-4 py-3 dark:border-gray-800">
          <div className="text-2xl font-semibold">
            {report.scopes_complete} / {report.scopes_total}
          </div>
          <div className="text-sm text-gray-500">scopes fully inspected</div>
        </div>
        <div className="min-w-36 rounded-lg border border-gray-200 px-4 py-3 dark:border-gray-800">
          <div className="text-2xl font-semibold">{report.scopes_with_gaps}</div>
          <div className="text-sm text-gray-500">scopes with gaps</div>
        </div>
        <div className="min-w-36 rounded-lg border border-gray-200 px-4 py-3 dark:border-gray-800">
          <div className="text-2xl font-semibold">{report.scan_status}</div>
          <div className="text-sm text-gray-500">scan status</div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-gray-500 dark:bg-gray-900">
            <tr>
              {["Region", "Service", "Status", "Discovered", "Inspected", "Errors"].map((title) => (
                <th key={title} className="px-3 py-2 font-medium">
                  {title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.scopes.map((scope) => (
              <tr
                key={`${scope.region}/${scope.service}`}
                className="border-t border-gray-200 dark:border-gray-800"
              >
                <td className="px-3 py-2">{scope.region}</td>
                <td className="px-3 py-2">{scope.service}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      STATUS_TONE[scope.status] ?? "bg-gray-100 dark:bg-gray-800"
                    }`}
                  >
                    {scope.status}
                  </span>
                </td>
                <td className="px-3 py-2">{scope.resources_discovered}</td>
                <td className="px-3 py-2">{scope.resources_inspected}</td>
                <td className="px-3 py-2">
                  {scope.errors.map((e) => `${e.code} on ${e.operation}`).join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}