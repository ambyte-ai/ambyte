"use client";

import { AlertTriangle, ArrowRight, ShieldAlert, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
	useRiskResources,
	type ResourceRiskItem,
} from "@/hooks/use-risk-resources";
import { cn } from "@/lib/utils";

interface RiskListProps {
	className?: string;
}

/**
 * Determines if a resource is critical based on sensitivity or risk level.
 */
function isCritical(item: ResourceRiskItem): boolean {
	const criticalValues = [
		"RESTRICTED",
		"CONFIDENTIAL",
		"HIGH",
		"UNACCEPTABLE",
		"4",
		"3",
	];
	return (
		criticalValues.includes(item.sensitivity.toUpperCase()) ||
		criticalValues.includes(item.risk_level.toUpperCase())
	);
}

/**
 * Generates a human-readable risk description based on the resource attributes.
 */
function getRiskDescription(item: ResourceRiskItem): string {
	const sens = item.sensitivity.toUpperCase();
	const risk = item.risk_level.toUpperCase();

	if (sens === "RESTRICTED" || sens === "4") {
		return "Restricted data requires strict access controls and monitoring.";
	}
	if (sens === "CONFIDENTIAL" || sens === "3") {
		return "Confidential data detected — verify policy coverage.";
	}
	if (risk === "UNACCEPTABLE" || risk === "4") {
		return "Unacceptable risk level — immediate action required.";
	}
	if (risk === "HIGH" || risk === "3") {
		return "High risk resource flagged for governance review.";
	}
	return "Resource flagged for potential governance issues.";
}

export function RiskList({ className }: RiskListProps) {
	const { resources, isLoading } = useRiskResources(10);

	if (isLoading) {
		return <RiskListSkeleton className={className} />;
	}

	if (!resources || resources.length === 0) {
		return <EmptyState className={className} />;
	}

	return (
		<Card className={cn("border-border/50 flex flex-col", className)}>
			<CardHeader className="pb-2">
				<div className="flex items-center justify-between">
					<div className="space-y-1">
						<CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground/70 flex items-center gap-2">
							<Zap className="h-4 w-4 text-amber-500" />
							Inventory Risks
						</CardTitle>
						<CardDescription className="text-xs">
							Resources needing governance attention.
						</CardDescription>
					</div>
					<Button variant="ghost" size="sm" className="h-7 w-7 p-0">
						<ArrowRight className="h-4 w-4 text-muted-foreground" />
					</Button>
				</div>
			</CardHeader>
			<CardContent className="flex-1 px-0 pb-0">
				<div className="divide-y divide-border/30">
					{resources.map((item) => (
						<div
							key={item.urn}
							className="group flex items-start gap-3 p-4 hover:bg-muted/30 transition-colors"
						>
							{/* Icon Indicator */}
							<div className="mt-0.5 shrink-0">
								{isCritical(item) ? (
									<ShieldAlert className="h-4 w-4 text-rose-500" />
								) : (
									<AlertTriangle className="h-4 w-4 text-amber-500" />
								)}
							</div>

							{/* Content */}
							<div className="flex-1 space-y-1 min-w-0">
								<div className="flex items-center justify-between gap-2">
									<p
										className="font-mono text-xs font-medium text-foreground truncate"
										title={item.urn}
									>
										{item.name || item.urn}
									</p>
									<Button
										variant="outline"
										size="sm"
										className="h-6 text-[10px] px-2 opacity-0 group-hover:opacity-100 transition-opacity"
									>
										Fix
										{/*//TODO: add fix functionality*/}
									</Button>
								</div>
								<div className="flex items-center gap-2 text-[10px] text-muted-foreground">
									<span className="font-mono uppercase">{item.platform}</span>
									{item.sensitivity !== "UNSPECIFIED" && (
										<>
											<span>•</span>
											<span className="text-amber-500">{item.sensitivity}</span>
										</>
									)}
									{item.risk_level !== "UNSPECIFIED" && (
										<>
											<span>•</span>
											<span className="text-rose-400">{item.risk_level}</span>
										</>
									)}
								</div>
								<p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
									{getRiskDescription(item)}
								</p>
							</div>
						</div>
					))}
				</div>
			</CardContent>
			{/* Footer / Summary */}
			<div className="p-4 border-t border-border/30 bg-muted/10">
				<p className="text-[10px] text-muted-foreground text-center">
					{resources.length} resource{resources.length !== 1 ? "s" : ""} flagged
					for attention.
				</p>
			</div>
		</Card>
	);
}

function RiskListSkeleton({ className }: { className?: string }) {
	return (
		<Card className={cn("border-border/50", className)}>
			<CardHeader>
				<Skeleton className="h-4 w-32 bg-muted" />
				<Skeleton className="h-3 w-48 bg-muted mt-2" />
			</CardHeader>
			<CardContent className="px-0">
				<div className="divide-y divide-border/30">
					{Array.from({ length: 3 }).map((_, i) => (
						<div key={i} className="p-4 flex gap-3">
							<Skeleton className="h-4 w-4 rounded bg-muted" />
							<div className="flex-1 space-y-2">
								<Skeleton className="h-3 w-3/4 bg-muted" />
								<Skeleton className="h-3 w-full bg-muted" />
							</div>
						</div>
					))}
				</div>
			</CardContent>
		</Card>
	);
}

function EmptyState({ className }: { className?: string }) {
	return (
		<Card
			className={cn(
				"border-border/50 flex flex-col justify-center items-center h-full min-h-[300px]",
				className,
			)}
		>
			<div className="text-center space-y-3 px-6">
				<div className="h-10 w-10 rounded-full bg-emerald-500/10 flex items-center justify-center mx-auto">
					<ShieldAlert className="h-5 w-5 text-emerald-500" />
				</div>
				<h3 className="text-sm font-medium text-foreground">All Clear</h3>
				<p className="text-xs text-muted-foreground">
					No high-risk resources detected in your inventory.
				</p>
			</div>
		</Card>
	);
}
