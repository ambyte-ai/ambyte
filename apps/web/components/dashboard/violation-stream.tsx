"use client";

import { AlertOctagon, ArrowUpRight, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import type { RecentBlock } from "@/hooks/use-ambyte-stats";
import { cn } from "@/lib/utils";

interface ViolationStreamProps {
	data?: RecentBlock[];
	isLoading?: boolean;
	className?: string;
}

export function ViolationStream({
	data = [],
	isLoading,
	className,
}: ViolationStreamProps) {
	if (isLoading) {
		return <ViolationStreamSkeleton className={className} />;
	}

	if (!data.length) {
		return <EmptyState className={className} />;
	}

	return (
		<Card className={cn("border-border/50", className)}>
			<CardHeader className="flex flex-row items-center justify-between pb-2">
				<div className="space-y-1">
					<CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground/70 flex items-center gap-2">
						<ShieldAlert className="h-4 w-4 text-rose-500" />
						Recent Violations
					</CardTitle>
					<CardDescription className="text-xs">
						Real-time feed of blocked access attempts.
					</CardDescription>
				</div>
				<Button variant="outline" size="sm" className="h-7 text-xs gap-1">
					View All
					<ArrowUpRight className="h-3 w-3 opacity-50" />
				</Button>
			</CardHeader>
			<CardContent className="p-0">
				<Table>
					<TableHeader>
						<TableRow className="hover:bg-transparent border-border/50">
							<TableHead className="w-[100px] text-xs font-medium">
								Time
							</TableHead>
							<TableHead className="w-[140px] text-xs font-medium">
								Actor
							</TableHead>
							<TableHead className="w-[100px] text-xs font-medium">
								Action
							</TableHead>
							<TableHead className="text-xs font-medium">
								Resource & Reason
							</TableHead>
							<TableHead className="w-[50px]" />
						</TableRow>
					</TableHeader>
					<TableBody>
						{data.map((block) => (
							<TableRow
								key={block.id}
								className="group cursor-pointer hover:bg-muted/30 border-border/40 transition-colors"
								onClick={() => console.log("Open proof modal for", block.id)}
								//TODO: Open proof modal
							>
								{/* Timestamp */}
								<TableCell className="py-2 text-xs font-mono text-muted-foreground whitespace-nowrap">
									{new Date(block.timestamp).toLocaleTimeString([], {
										hour: "2-digit",
										minute: "2-digit",
										second: "2-digit",
									})}
								</TableCell>

								{/* Actor */}
								<TableCell className="py-2">
									<div className="flex items-center gap-2 max-w-[140px]">
										<span
											className="truncate font-mono text-xs text-foreground/90"
											title={block.actor_id}
										>
											{block.actor_id}
										</span>
									</div>
								</TableCell>

								{/* Action */}
								<TableCell className="py-2">
									<Badge
										variant="outline"
										className="font-mono text-[10px] font-normal border-rose-500/20 text-rose-400 bg-rose-500/5 px-1.5 py-0"
									>
										{block.action}
									</Badge>
								</TableCell>

								{/* Resource & Reason */}
								<TableCell className="py-2 max-w-[200px]">
									<div className="flex flex-col gap-0.5">
										<span
											className="truncate font-mono text-[10px] text-muted-foreground"
											title={block.resource_urn}
										>
											{block.resource_urn}
										</span>
										{block.reason_summary && (
											<span
												className="truncate text-xs text-rose-400/90"
												title={block.reason_summary}
											>
												{block.reason_summary}
											</span>
										)}
									</div>
								</TableCell>

								{/* Action Icon */}
								<TableCell className="py-2 text-right">
									<AlertOctagon className="h-4 w-4 text-muted-foreground/30 group-hover:text-rose-500 transition-colors" />
								</TableCell>
							</TableRow>
						))}
					</TableBody>
				</Table>
			</CardContent>
		</Card>
	);
}

function ViolationStreamSkeleton({ className }: { className?: string }) {
	return (
		<Card className={cn("border-border/50", className)}>
			<CardHeader className="pb-4">
				<Skeleton className="h-4 w-40 bg-muted" />
				<Skeleton className="h-3 w-64 bg-muted mt-2" />
			</CardHeader>
			<CardContent className="px-0">
				<div className="space-y-0 divide-y divide-border/30">
					{Array.from({ length: 5 }).map((_, i) => (
						<div key={i} className="flex items-center gap-4 p-4">
							<Skeleton className="h-3 w-16 bg-muted" />
							<Skeleton className="h-3 w-24 bg-muted" />
							<Skeleton className="h-4 w-12 rounded-full bg-muted" />
							<Skeleton className="h-3 flex-1 bg-muted" />
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
				"border-border/50 flex flex-col justify-center items-center h-[350px]",
				className,
			)}
		>
			<div className="text-center space-y-3 max-w-sm px-6">
				<div className="h-12 w-12 rounded-full bg-emerald-500/10 flex items-center justify-center mx-auto mb-2">
					<ShieldAlert className="h-6 w-6 text-emerald-500" />
				</div>
				<h3 className="text-lg font-medium text-foreground">Clean Record</h3>
				<p className="text-sm text-muted-foreground">
					No blocking events detected in the last 24 hours. Your policies are
					either permissive or being respected.
				</p>
			</div>
		</Card>
	);
}
