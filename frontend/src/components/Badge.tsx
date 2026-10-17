// One small component for every verdict, approval and risk label.
// Text is rendered through React, which escapes it, so resource data can't inject HTML.

const TONES = {
  red: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  green: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  blue: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  grey: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
} as const;

type Tone = keyof typeof TONES;

const VERDICT_TONE: Record<string, Tone> = {
  ai_confirmed: "blue",
  ai_suspected: "amber",
  unknown: "grey",
  not_ai_evidenced: "grey",
};

const APPROVAL_TONE: Record<string, Tone> = {
  approved: "green",
  potential_shadow_ai: "red",
  governance_exception: "amber",
  not_assessed: "grey",
};

const RISK_TONE: Record<string, Tone> = {
  high: "red",
  medium: "amber",
  low: "green",
  unassessed: "grey",
};

function Badge({ value, tone }: { value: string; tone: Tone }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}

export const VerdictBadge = ({ value }: { value: string }) => (
  <Badge value={value} tone={VERDICT_TONE[value] ?? "grey"} />
);

export const ApprovalBadge = ({ value }: { value: string }) => (
  <Badge value={value} tone={APPROVAL_TONE[value] ?? "grey"} />
);

export const RiskBadge = ({ value }: { value: string }) => (
  <Badge value={value} tone={RISK_TONE[value] ?? "grey"} />
);