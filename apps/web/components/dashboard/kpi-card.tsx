import { ArrowDown, ArrowRight, ArrowUp, type LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface KpiCardProps {
	title: string;
	/**
	 * The main metric to display.
	 * Typically a number or percentage string.
	 */
	value: string | number;
	/**
	 * Icon to display in the top right.
	 */
	icon?: LucideIcon;
	/**
	 * Contextual text below the value (e.g. "3 Blocking, 11 Audit-Only").
	 */
	subtext?: string;
	/**
	 * Direction of the trend.
	 */
	trend?: "up" | "down" | "neutral";
	/**
	 * The text value of the trend (e.g. "+5%").
	 */
	trendValue?: string;
	/**
	 * Semantic color state.
	 * - Default: Foreground color (White/Zinc-100)
	 * - Success: Emerald-500
	 * - Warning: Amber-500
	 * - Error: Rose-500
	 */
	status?: "default" | "success" | "warning" | "error";
	isLoading?: boolean;
	className?: string;
}

export function KpiCard({
	title,
	value,
	icon: Icon,
	subtext,
	trend,
	trendValue,
	status = "default",
	isLoading = false,
	className,
}: KpiCardProps) {
	if (isLoading) {
		return <KpiCardSkeleton />;
	}

	// Resolve text color based on status
	const valueColorStyles = {
		default: "text-foreground",
		success: "text-emerald-500", // Matches Tailwind config 'success'
		warning: "text-amber-500", // Matches Tailwind config 'warning'
		error: "text-rose-500", // Matches Tailwind config 'error'
	};

	// Resolve trend icon and color
	const TrendIcon =
		trend === "up" ? ArrowUp : trend === "down" ? ArrowDown : ArrowRight;

	const trendColor =
		trend === "up"
			? "text-emerald-500"
			: trend === "down"
				? "text-rose-500"
				: "text-muted-foreground";

	return (
		<Card
			className={cn(
				"relative overflow-hidden border-border/50 bg-card p-5 transition-all hover:border-border",
				className,
			)}
		>
			{/* Header: Title + Icon */}
			<div className="flex items-center justify-between">
				<p className="text-sm font-medium text-muted-foreground tracking-wide uppercase text-[11px]">
					{title}
				</p>
				{Icon && <Icon className="h-4 w-4 text-muted-foreground/50" />}
			</div>

			{/* Body: Value */}
			<div className="mt-3 flex items-baseline gap-2">
				<h3
					className={cn(
						"text-2xl font-mono font-medium tracking-tight",
						valueColorStyles[status],
					)}
				>
					{value}
				</h3>
			</div>

			{/* Footer: Trend + Subtext */}
			{(subtext || trendValue) && (
				<div className="mt-3 flex items-center gap-2 text-xs">
					{trendValue && (
						<div
							className={cn(
								"flex items-center gap-0.5 font-medium",
								trendColor,
							)}
						>
							<TrendIcon className="h-3 w-3" />
							<span>{trendValue}</span>
						</div>
					)}
					{subtext && (
						<p className="text-muted-foreground truncate">{subtext}</p>
					)}
				</div>
			)}
		</Card>
	);
}

function KpiCardSkeleton() {
	return (
		<Card className="p-5 border-border/50">
			<div className="flex justify-between items-center">
				<Skeleton className="h-3 w-20 bg-muted" />
				<Skeleton className="h-4 w-4 bg-muted" />
			</div>
			<div className="mt-4">
				<Skeleton className="h-8 w-1/2 bg-muted" />
			</div>
			<div className="mt-4">
				<Skeleton className="h-3 w-3/4 bg-muted" />
			</div>
		</Card>
	);
}
