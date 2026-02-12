import { Hash, Settings2, Shield } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
	PRIVACY_METHOD_LABELS,
	type PrivacyEnhancementRule,
	PrivacyMethod,
} from "@/types/obligation";

interface PrivacyVisualizerProps {
	rule: PrivacyEnhancementRule;
}

export function PrivacyVisualizer({ rule }: PrivacyVisualizerProps) {
	const methodLabel = PRIVACY_METHOD_LABELS[rule.method] || "Unknown Method";
	const hasParams = rule.parameters && Object.keys(rule.parameters).length > 0;

	return (
		<div className="flex flex-col gap-4">
			{/* Method Header */}
			<div className="flex items-center gap-4 p-4 border rounded-lg bg-card text-card-foreground shadow-sm">
				<div className="flex h-10 w-10 items-center justify-center rounded-full bg-violet-100 dark:bg-violet-900/20">
					<Shield className="h-5 w-5 text-violet-600 dark:text-violet-400" />
				</div>

				<div className="flex-1 space-y-1">
					<p className="text-sm font-medium leading-none text-muted-foreground">
						Privacy Method
					</p>
					<div className="flex items-center gap-2">
						<span className="text-lg font-semibold tracking-tight">
							{methodLabel}
						</span>
						{/* Optional: Add a badge for specific method types if needed */}
						{rule.method === PrivacyMethod.DIFFERENTIAL_PRIVACY && (
							<Badge
								variant="secondary"
								className="bg-violet-100/50 text-violet-700 border-violet-200 dark:bg-violet-900/30 dark:text-violet-300 dark:border-violet-800"
							>
								Advanced
							</Badge>
						)}
					</div>
				</div>
			</div>

			{/* Parameters Grid */}
			<div className="rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden">
				<div className="flex items-center gap-2 p-3 border-b bg-muted/40">
					<Settings2 className="h-4 w-4 text-muted-foreground" />
					<h3 className="font-semibold text-sm">Configuration Parameters</h3>
				</div>

				{hasParams ? (
					<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px bg-border">
						{Object.entries(rule.parameters).map(([key, value]) => (
							<div key={key} className="bg-background p-3 flex flex-col gap-1">
								<span className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
									<Hash className="h-3 w-3 opacity-50" />
									{key}
								</span>
								<code className="text-sm font-mono truncate" title={value}>
									{value}
								</code>
							</div>
						))}
					</div>
				) : (
					<div className="p-8 text-center text-sm text-muted-foreground italic">
						No additional parameters configured.
					</div>
				)}
			</div>
		</div>
	);
}
