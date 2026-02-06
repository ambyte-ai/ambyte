"use client";

import { useMemo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DenyReasonAgg } from "@/hooks/use-ambyte-stats";
import { cn } from "@/lib/utils";

interface ReasonChartProps {
	data?: DenyReasonAgg[];
	isLoading?: boolean;
	className?: string;
}

// Map chart colors to CSS variables defined in global.css / tailwind config
const COLORS = [
	"hsl(var(--chart-1))", // Blue
	"hsl(var(--chart-2))", // Teal
	"hsl(var(--chart-3))", // Orange
	"hsl(var(--chart-4))", // Purple
	"hsl(var(--chart-5))", // Pink
];

export function ReasonChart({
	data = [],
	isLoading,
	className,
}: ReasonChartProps) {
	// Calculate total for percentage display or center text
	const total = useMemo(
		() => data.reduce((acc, curr) => acc + curr.count, 0),
		[data],
	);

	if (isLoading) {
		return <ReasonChartSkeleton className={className} />;
	}

	if (!data.length) {
		return <EmptyState className={className} />;
	}

	return (
		<Card className={cn("flex flex-col border-border/50", className)}>
			<CardHeader className="pb-2">
				<CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground/70">
					Denial Reasons
				</CardTitle>
			</CardHeader>
			<CardContent className="flex-1 flex items-center p-0">
				<div className="grid grid-cols-2 w-full h-full">
					{/* Left: The Chart */}
					<div className="relative h-[180px] w-full flex items-center justify-center">
						<ResponsiveContainer width="100%" height="100%">
							<PieChart>
								<Pie
									data={data}
									cx="50%"
									cy="50%"
									innerRadius={55}
									outerRadius={75}
									paddingAngle={2}
									dataKey="count"
									stroke="none"
								>
									{data.map((_, index) => (
										<Cell
											key={`cell-${index}`}
											fill={COLORS[index % COLORS.length]}
											className="stroke-background hover:opacity-80 transition-opacity"
										/>
									))}
								</Pie>
								<Tooltip
									content={({ active, payload }) => {
										if (active && payload && payload.length) {
											const item = payload[0].payload;
											return (
												<div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-xl text-popover-foreground text-xs">
													<span className="font-medium text-foreground">
														{item.reason}
													</span>
													<div className="flex gap-2 text-muted-foreground mt-1">
														<span>{item.count} events</span>
														<span>
															({((item.count / total) * 100).toFixed(1)}%)
														</span>
													</div>
												</div>
											);
										}
										return null;
									}}
								/>
							</PieChart>
						</ResponsiveContainer>
						{/* Center Label */}
						<div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
							<span className="text-2xl font-bold font-mono text-foreground">
								{total}
							</span>
							<span className="text-[10px] uppercase text-muted-foreground font-medium">
								Blocked
							</span>
						</div>
					</div>

					{/* Right: The Legend */}
					<div className="flex flex-col justify-center gap-3 pr-6 text-xs">
						{data.slice(0, 5).map((item, index) => (
							<div
								key={item.reason}
								className="flex items-center justify-between gap-2 w-full"
							>
								<div className="flex items-center gap-2 min-w-0">
									<div
										className="h-2.5 w-2.5 rounded-full shrink-0"
										style={{ backgroundColor: COLORS[index % COLORS.length] }}
									/>
									<span
										className="truncate text-muted-foreground"
										title={item.reason}
									>
										{item.reason}
									</span>
								</div>
								<span className="font-mono font-medium text-foreground">
									{Math.round((item.count / total) * 100)}%
								</span>
							</div>
						))}
					</div>
				</div>
			</CardContent>
		</Card>
	);
}

function ReasonChartSkeleton({ className }: { className?: string }) {
	return (
		<Card className={cn("border-border/50", className)}>
			<CardHeader>
				<Skeleton className="h-4 w-32 bg-muted" />
			</CardHeader>
			<CardContent className="h-[180px] grid grid-cols-2 items-center">
				<div className="flex justify-center">
					<Skeleton className="h-32 w-32 rounded-full bg-muted/20" />
				</div>
				<div className="space-y-3 pr-6">
					<Skeleton className="h-3 w-full bg-muted" />
					<Skeleton className="h-3 w-3/4 bg-muted" />
					<Skeleton className="h-3 w-1/2 bg-muted" />
				</div>
			</CardContent>
		</Card>
	);
}

function EmptyState({ className }: { className?: string }) {
	return (
		<Card
			className={cn(
				"border-border/50 flex flex-col justify-center items-center h-[240px]",
				className,
			)}
		>
			<div className="text-center space-y-2">
				<div className="h-20 w-20 rounded-full border-4 border-muted/20 border-t-muted mx-auto" />
				<p className="text-xs text-muted-foreground">
					No denied requests found
				</p>
			</div>
		</Card>
	);
}
