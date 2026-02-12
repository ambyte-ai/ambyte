import {
	Brain,
	Check,
	Database,
	type LucideIcon,
	PenTool,
	Quote,
	Share2,
	X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AiModelConstraint } from "@/types/obligation";

interface AiModelVisualizerProps {
	rule: AiModelConstraint;
}

interface CapabilityItemProps {
	label: string;
	allowed: boolean;
	icon: LucideIcon;
	description: string;
}

function CapabilityItem({
	label,
	allowed,
	icon: Icon,
	description,
}: CapabilityItemProps) {
	return (
		<div
			className={cn(
				"flex items-start gap-4 p-4 rounded-lg border transition-colors",
				allowed
					? "bg-emerald-50/50 border-emerald-200/50 dark:bg-emerald-950/10 dark:border-emerald-900/50"
					: "bg-rose-50/50 border-rose-200/50 dark:bg-rose-950/10 dark:border-rose-900/50",
			)}
		>
			<div
				className={cn(
					"flex h-10 w-10 shrink-0 items-center justify-center rounded-full border",
					allowed
						? "bg-emerald-100 border-emerald-200 text-emerald-600 dark:bg-emerald-900/30 dark:border-emerald-800 dark:text-emerald-400"
						: "bg-rose-100 border-rose-200 text-rose-600 dark:bg-rose-900/30 dark:border-rose-800 dark:text-rose-400",
				)}
			>
				<Icon className="h-5 w-5" />
			</div>

			<div className="space-y-1">
				<div className="flex items-center gap-2">
					<h4 className="flex items-center gap-2 font-semibold text-sm">
						{label}
						{allowed ? (
							<Badge
								variant="outline"
								className="h-5 px-1.5 bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800"
							>
								<Check className="h-3 w-3 mr-1" /> Allowed
							</Badge>
						) : (
							<Badge
								variant="outline"
								className="h-5 px-1.5 bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-800"
							>
								<X className="h-3 w-3 mr-1" /> Denied
							</Badge>
						)}
					</h4>
				</div>
				<p className="text-xs text-muted-foreground leading-relaxed">
					{description}
				</p>
			</div>
		</div>
	);
}

export function AiModelVisualizer({ rule }: AiModelVisualizerProps) {
	return (
		<div className="flex flex-col gap-6">
			<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
				<CapabilityItem
					label="Model Training"
					allowed={rule.training_allowed}
					icon={Brain}
					description="Permission to use data for training foundation models."
				/>

				<CapabilityItem
					label="Fine-Tuning"
					allowed={rule.fine_tuning_allowed}
					icon={PenTool}
					description="Permission to use data for fine-tuning existing models."
				/>

				<CapabilityItem
					label="RAG Usage"
					allowed={rule.rag_usage_allowed}
					icon={Database}
					description="Permission to use data in Retrieval-Augmented Generation flows."
				/>

				<CapabilityItem
					label="Open Release Required"
					allowed={rule.requires_open_source_release}
					icon={Share2}
					description={
						rule.requires_open_source_release
							? "Models trained on this data MUST be open-sourced."
							: "No requirement to open-source derived models."
					}
				/>
			</div>

			{rule.attribution_text_required && (
				<div className="rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden">
					<div className="flex items-center gap-2 p-3 border-b bg-muted/40">
						<Quote className="h-4 w-4 text-primary" />
						<h3 className="font-semibold text-sm">Required Attribution</h3>
					</div>
					<div className="p-4 bg-muted/20">
						<code className="text-sm font-mono text-muted-foreground block p-3 rounded bg-background border">
							{rule.attribution_text_required}
						</code>
					</div>
				</div>
			)}
		</div>
	);
}
