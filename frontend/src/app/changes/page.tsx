import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

function KeyList({ title, keys }: { title: string; keys: string[] }) {
  return (
    <section>
      <h2 className="mb-2 font-semibold">
        {title} ({keys.length})
      </h2>
      {keys.length === 0 ? (
        <p className="text-sm text-gray-500">None.</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {keys.map((key) => (
            <li key={key} className="break-all rounded border border-gray-200 px-3 py-1 dark:border-gray-800">
              {key}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default async function ChangesPage() {
  let report;
  try {
    report = await api.changes();
  } catch {
    return <p className="text-sm text-red-700 dark:text-red-300">Could not reach the API.</p>;
  }
  if (!report) return <p className="text-sm text-gray-500">No scans yet. Run a scan first.</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Changes since the previous scan</h1>
      <p className="text-sm text-gray-500">{report.note}</p>
      <KeyList title="New assets" keys={report.new_assets} />
      <KeyList title="Missing assets" keys={report.missing_assets} />
    </div>
  );
}