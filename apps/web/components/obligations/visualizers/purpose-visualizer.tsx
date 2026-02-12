import { Ban, Check, ListFilter, Target, X } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { PurposeRestriction } from "@/types/obligation";

interface PurposeVisualizerProps {
	rule: PurposeRestriction;
}

export function PurposeVisualizer({ rule }: PurposeVisualizerProps) {
	const hasAllowed = rule.allowed_purposes && rule.allowed_purposes.length > 0;
	const hasDenied = rule.denied_purposes && rule.denied_purposes.length > 0;

	return (
		<div className="flex flex-col gap-4">
			{/* Header / Summary */}
			<div className="flex items-center gap-2 mb-2">
				<Target className="h-4 w-4 text-muted-foreground" />
				<span className="text-sm font-medium text-muted-foreground">
					Purpose Restrictions
				</span>
			</div>

			<div className="grid gap-4 sm:grid-cols-2">
				{/* Allowed Purposes */}
				<div
					className={cn(
						"rounded-lg border bg-card text-card-foreground shadow-sm",
						!hasAllowed && "opacity-50 border-dashed",
					)}
				>
					<div className="flex items-center gap-2 p-3 border-b bg-emerald-50/50 dark:bg-emerald-950/20">
						<div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/30">
							<Check className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
						</div>
						<h3 className="font-semibold text-sm">Allowed Purposes</h3>
						<span className="ml-auto text-xs text-muted-foreground bg-background px-2 py-0.5 rounded-full border">
							{rule.allowed_purposes?.length || 0}
						</span>
					</div>

					<ScrollArea className="h-[200px] p-3">
						{hasAllowed ? (
							<ul className="space-y-2">
								{rule.allowed_purposes.map((purpose) => (
									<li key={purpose} className="flex items-center gap-2 text-sm">
										<div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100/50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400">
											<ListFilter className="h-3 w-3" />
										</div>
										<span className="font-medium">{purpose}</span>
									</li>
								))}
							</ul>
						) : (
							<div className="flex h-full items-center justify-center text-xs text-muted-foreground italic">
								No specific purposes allowed
							</div>
						)}
					</ScrollArea>
				</div>

				{/* Denied Purposes */}
				<div
					className={cn(
						"rounded-lg border bg-card text-card-foreground shadow-sm",
						!hasDenied && "opacity-50 border-dashed",
					)}
				>
					<div className="flex items-center gap-2 p-3 border-b bg-rose-50/50 dark:bg-rose-950/20">
						<div className="flex h-8 w-8 items-center justify-center rounded-full bg-rose-100 dark:bg-rose-900/30">
							<X className="h-4 w-4 text-rose-600 dark:text-rose-400" />
						</div>
						<h3 className="font-semibold text-sm">Denied Purposes</h3>
						<span className="ml-auto text-xs text-muted-foreground bg-background px-2 py-0.5 rounded-full border">
							{rule.denied_purposes?.length || 0}
						</span>
					</div>

					<ScrollArea className="h-[200px] p-3">
						{hasDenied ? (
							<ul className="space-y-2">
								{rule.denied_purposes.map((purpose) => (
									<li
										key={purpose}
										className="flex items-center gap-2 text-sm text-muted-foreground"
									>
										<div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-100/50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400">
											<Ban className="h-3 w-3" />
										</div>
										<span className="line-through decoration-rose-500/50 font-medium">
											{purpose}
										</span>
									</li>
								))}
							</ul>
						) : (
							<div className="flex h-full items-center justify-center text-xs text-muted-foreground italic">
								No specific purposes denied
							</div>
						)}
					</ScrollArea>
				</div>
			</div>
		</div>
	);
}
