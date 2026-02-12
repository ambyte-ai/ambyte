import { Check, Globe, ShieldAlert, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatRegionName } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import type { GeofencingRule } from "@/types/obligation";

interface GeofencingVisualizerProps {
	rule: GeofencingRule;
}

export function GeofencingVisualizer({ rule }: GeofencingVisualizerProps) {
	const hasAllowed = rule.allowed_regions && rule.allowed_regions.length > 0;
	const hasDenied = rule.denied_regions && rule.denied_regions.length > 0;

	return (
		<div className="flex flex-col gap-4">
			{/* Header / Summary */}
			<div className="flex items-center gap-2 mb-2">
				<Globe className="h-4 w-4 text-muted-foreground" />
				<span className="text-sm font-medium text-muted-foreground">
					Geofencing Controls
				</span>
				{rule.strict_residency && (
					<Badge
						variant="outline"
						className="ml-auto gap-1 border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-400"
					>
						<ShieldAlert className="h-3 w-3" />
						Strict Residency
					</Badge>
				)}
			</div>

			<div className="grid gap-4 sm:grid-cols-2">
				{/* Allowed Regions */}
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
						<h3 className="font-semibold text-sm">Allowed Regions</h3>
						<span className="ml-auto text-xs text-muted-foreground bg-background px-2 py-0.5 rounded-full border">
							{rule.allowed_regions?.length || 0}
						</span>
					</div>

					<ScrollArea className="h-[200px] p-3">
						{hasAllowed ? (
							<ul className="space-y-2">
								{rule.allowed_regions.map((code) => (
									<li key={code} className="flex items-center gap-2 text-sm">
										<div className="relative flex items-center justify-center w-6 h-4 overflow-hidden rounded-[2px] border bg-muted">
											{/* Flag placeholder or just code */}
											<span className="text-[9px] font-bold text-muted-foreground">
												{code}
											</span>
										</div>
										<span>{formatRegionName(code)}</span>
									</li>
								))}
							</ul>
						) : (
							<div className="flex h-full items-center justify-center text-xs text-muted-foreground italic">
								No specific regions allowed
							</div>
						)}
					</ScrollArea>
				</div>

				{/* Denied Regions */}
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
						<h3 className="font-semibold text-sm">Denied Regions</h3>
						<span className="ml-auto text-xs text-muted-foreground bg-background px-2 py-0.5 rounded-full border">
							{rule.denied_regions?.length || 0}
						</span>
					</div>

					<ScrollArea className="h-[200px] p-3">
						{hasDenied ? (
							<ul className="space-y-2">
								{rule.denied_regions.map((code) => (
									<li
										key={code}
										className="flex items-center gap-2 text-sm text-muted-foreground"
									>
										<div className="relative flex items-center justify-center w-6 h-4 overflow-hidden rounded-[2px] border bg-muted opacity-70">
											<span className="text-[9px] font-bold text-muted-foreground">
												{code}
											</span>
										</div>
										<span className="line-through decoration-rose-500/50">
											{formatRegionName(code)}
										</span>
									</li>
								))}
							</ul>
						) : (
							<div className="flex h-full items-center justify-center text-xs text-muted-foreground italic">
								No specific regions denied
							</div>
						)}
					</ScrollArea>
				</div>
			</div>
		</div>
	);
}
