"use client";

import { useMemo } from "react";
import {
	Bar,
	BarChart,
	CartesianGrid,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { TrafficPoint } from "@/hooks/use-ambyte-stats";
import { cn } from "@/lib/utils";

interface TrafficChartProps {
	data?: TrafficPoint[];
	isLoading?: boolean;
	className?: string;
}

export function TrafficChart({
	data = [],
	isLoading,
	className,
}: TrafficChartProps) {
	// Format data for the chart (parse ISO strings to readable times)
	const chartData = useMemo(() => {
		return data.map((point) => {
			const date = new Date(point.timestamp);
			return {
				...point,
				// Format: "10:00" or "Oct 24" depending on range,
				// simplified to time for the 24h view default
				displayTime: date.toLocaleTimeString([], {
					hour: "2-digit",
					minute: "2-digit",
				}),
				fullDate: date.toLocaleString(),
			};
		});
	}, [data]);

	if (isLoading) {
		return <TrafficChartSkeleton className={className} />;
	}

	if (!data.length) {
		return <EmptyState className={className} />;
	}

	return (
		<Card className={cn("flex flex-col border-border/50", className)}>
			<CardHeader className="pb-4">
				<div className="flex items-center justify-between">
					<CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground/70">
						Traffic & Decisions
					</CardTitle>
					{/* Legend could go here TODO*/}
					<div className="flex gap-4 text-xs font-medium">
						<div className="flex items-center gap-1.5">
							<div className="h-2 w-2 rounded-full bg-emerald-500" />
							<span className="text-muted-foreground">Allowed</span>
						</div>
						<div className="flex items-center gap-1.5">
							<div className="h-2 w-2 rounded-full bg-rose-500" />
							<span className="text-muted-foreground">Denied</span>
						</div>
					</div>
				</div>
			</CardHeader>
			<CardContent className="flex-1 min-h-[300px] w-full pl-0">
				<ResponsiveContainer width="100%" height="100%">
					<BarChart
						data={chartData}
						margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
					>
						<CartesianGrid
							strokeDasharray="3 3"
							vertical={false}
							stroke="hsl(var(--border))"
							opacity={0.4}
						/>
						<XAxis
							dataKey="displayTime"
							stroke="#888888"
							fontSize={11}
							tickLine={false}
							axisLine={false}
							tickMargin={10}
							minTickGap={30}
						/>
						<YAxis
							stroke="#888888"
							fontSize={11}
							tickLine={false}
							axisLine={false}
							tickFormatter={(value) => `${value}`}
						/>
						<Tooltip
							content={({ active, payload, label }) => {
								if (active && payload && payload.length) {
									// Access the original data point from the payload
									const point = payload[0].payload;
									return (
										<div className="rounded-lg border border-border bg-popover p-3 shadow-xl text-popover-foreground text-xs">
											<div className="mb-2 font-mono font-medium text-muted-foreground">
												{point.fullDate}
											</div>
											<div className="flex flex-col gap-1.5">
												<div className="flex items-center justify-between gap-8">
													<div className="flex items-center gap-2">
														<div className="h-2 w-2 rounded-full bg-rose-500" />
														<span>Denied</span>
													</div>
													<span className="font-mono font-bold text-rose-500">
														{point.denied_count}
													</span>
												</div>
												<div className="flex items-center justify-between gap-8">
													<div className="flex items-center gap-2">
														<div className="h-2 w-2 rounded-full bg-emerald-500" />
														<span>Allowed</span>
													</div>
													<span className="font-mono font-bold text-emerald-500">
														{point.allowed_count}
													</span>
												</div>
											</div>
										</div>
									);
								}
								return null;
							}}
							cursor={{ fill: "hsl(var(--muted))", opacity: 0.2 }}
						/>
						<Bar
							dataKey="allowed_count"
							stackId="a"
							fill="var(--success)" // Using CSS var defined in tailwind config or mapped here
							className="fill-emerald-500"
							radius={[0, 0, 4, 4]}
							barSize={20}
						/>
						<Bar
							dataKey="denied_count"
							stackId="a"
							fill="var(--destructive)"
							className="fill-rose-500"
							radius={[4, 4, 0, 0]}
							barSize={20}
						/>
					</BarChart>
				</ResponsiveContainer>
			</CardContent>
		</Card>
	);
}

function TrafficChartSkeleton({ className }: { className?: string }) {
	return (
		<Card className={cn("border-border/50", className)}>
			<CardHeader>
				<Skeleton className="h-4 w-32 bg-muted" />
			</CardHeader>
			<CardContent className="h-[300px] flex items-end justify-between gap-2 px-6 pb-6">
				{/* Generate random height bars for skeleton effect */}
				{Array.from({ length: 12 }).map((_, i) => (
					<Skeleton
						key={i}
						className="w-full bg-muted/30"
						style={{ height: `${Math.random() * 60 + 20}%` }}
					/>
				))}
			</CardContent>
		</Card>
	);
}

function EmptyState({ className }: { className?: string }) {
	return (
		<Card
			className={cn(
				"border-border/50 flex flex-col justify-center items-center h-[400px]",
				className,
			)}
		>
			<div className="text-center space-y-2">
				<h3 className="text-lg font-medium text-foreground">No Traffic Data</h3>
				<p className="text-sm text-muted-foreground max-w-xs mx-auto">
					Connect a data source or run a check via the CLI to see activity here.
				</p>
			</div>
		</Card>
	);
}
