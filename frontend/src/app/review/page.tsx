import ReviewQueue from "@/components/ReviewQueue";
import { api, type QueueItem } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  let items: QueueItem[];
  try {
    items = await api.reviewQueue();
  } catch {
    return <p className="text-sm text-red-700 dark:text-red-300">Could not reach the API.</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Review queue</h1>
      <p className="text-sm text-gray-500">
        Assets that need a person: unapproved AI, registered assets outside their approved scope, and
        anything an LLM weighed in on. Highest risk first.
      </p>
      <ReviewQueue items={items} />
    </div>
  );
}