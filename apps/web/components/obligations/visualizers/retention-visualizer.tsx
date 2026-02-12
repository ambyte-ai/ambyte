import { CalendarClock, Clock, History } from "lucide-react";
import { formatIsoDuration } from "@/lib/formatters";
import { type RetentionRule, RetentionTrigger } from "@/types/obligation";

interface RetentionVisualizerProps {
	rule: RetentionRule;
}

const TRIGGER_LABELS: Record<RetentionTrigger, string> = {
	[RetentionTrigger.UNSPECIFIED]: "Unspecified",
	[RetentionTrigger.CREATION_DATE]: "Creation Date",
	[RetentionTrigger.LAST_ACCESS_DATE]: "Last Access Date",
	[RetentionTrigger.EVENT_DATE]: "Event Date",
	[RetentionTrigger.DATA_SUBJECT_REQUEST]: "Data Subject Request",
};

export function RetentionVisualizer({ rule }: RetentionVisualizerProps) {
	const readableDuration = formatIsoDuration(rule.duration);
	const triggerLabel = TRIGGER_LABELS[rule.trigger];

	return (
		<div className="flex flex-col gap-4">
			<div className="flex items-center gap-4 p-4 border rounded-lg bg-card text-card-foreground shadow-sm">
				<div className="flex h-10 w-10 items-center justify-center rounded-full bg-orange-100 dark:bg-orange-900/20">
					<Clock className="h-5 w-5 text-orange-600 dark:text-orange-400" />
				</div>

				<div className="flex-1 space-y-1">
					<p className="text-sm font-medium leading-none text-muted-foreground">
						Retention Period
					</p>
					<p className="text-lg font-semibold tracking-tight">
						{readableDuration || rule.duration}
					</p>
				</div>
			</div>

			<div className="flex items-center gap-4 p-4 border rounded-lg bg-card text-card-foreground shadow-sm">
				<div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/20">
					<CalendarClock className="h-5 w-5 text-blue-600 dark:text-blue-400" />
				</div>

				<div className="flex-1 space-y-1">
					<p className="text-sm font-medium leading-none text-muted-foreground">
						Trigger Event
					</p>
					<div className="flex items-center gap-2">
						<span className="font-medium">{triggerLabel}</span>
						{/* Optional: Add help text or tooltip for triggers if needed */}
					</div>
				</div>
			</div>

			{rule.allow_legal_hold_override && (
				<div className="flex items-center gap-2 px-4 py-2 text-xs text-muted-foreground bg-muted/50 rounded-md">
					<History className="h-3 w-3" />
					<span>Legal Hold Override Allowed</span>
				</div>
			)}
		</div>
	);
}
