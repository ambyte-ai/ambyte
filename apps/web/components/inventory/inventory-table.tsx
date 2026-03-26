"use client";

import {
	ChevronLeft,
	ChevronRight,
	Cloud,
	Copy,
	Database,
	Eye,
	FileJson,
	MoreHorizontal,
	Server,
	TerminalSquare,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import type { Resource } from "@/hooks/use-inventory";
import { cn } from "@/lib/utils";

interface InventoryTableProps {
	resources: Resource[];
	isLoading: boolean;
	pagination: {
		total: number;
		page: number;
		size: number;
		pages: number;
	};
	onPageChange: (page: number) => void;
	onRowClick: (resource: Resource) => void;
	hasActiveFilters: boolean;
}

// =============================================================================
// Helper Components & Functions
// =============================================================================

function PlatformIcon({ platform }: { platform: string }) {
	const p = platform.toLowerCase();
	if (p.includes("snowflake"))
		return <Database className="h-5 w-5 text-cyan-500" />;
	if (p.includes("databricks"))
		return <Server className="h-5 w-5 text-orange-500" />;
	if (p.includes("s3") || p.includes("aws"))
		return <Cloud className="h-5 w-5 text-yellow-500" />;
	if (p.includes("postgres"))
		return <Database className="h-5 w-5 text-blue-500" />;
	return <Server className="h-5 w-5 text-muted-foreground" />;
}

function SensitivityBadge({ resource }: { resource: Resource }) {
	// Extract sensitivity from attributes (or tags fallback)
	const rawSens =
		resource.attributes?.sensitivity ||
		resource.attributes?.tags?.sensitivity ||
		"UNSPECIFIED";

	const sensitivity = String(rawSens).toUpperCase();

	const styles: Record<string, string> = {
		PUBLIC: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
		INTERNAL: "bg-blue-500/10 text-blue-500 border-blue-500/20",
		CONFIDENTIAL: "bg-amber-500/10 text-amber-500 border-amber-500/20",
		RESTRICTED: "bg-rose-500/10 text-rose-500 border-rose-500/20",
		UNSPECIFIED: "bg-muted/30 text-muted-foreground border-border",
	};

	const style = styles[sensitivity] || styles.UNSPECIFIED;

	return (
		<Badge
			variant="outline"
			className={cn(
				"px-2 py-0.5 text-[10px] font-semibold tracking-wide",
				style,
			)}
		>
			{sensitivity}
		</Badge>
	);
}

function FormatTags({ tags }: { tags?: Record<string, string> }) {
	if (!tags || Object.keys(tags).length === 0) {
		return (
			<span className="text-[10px] text-muted-foreground italic">No tags</span>
		);
	}

	const entries = Object.entries(tags);
	const visibleTags = entries.slice(0, 2);
	const extraCount = entries.length - visibleTags.length;

	return (
		<div className="flex flex-wrap items-center gap-1.5">
			{visibleTags.map(([key, value]) => (
				<Badge
					key={key}
					variant="secondary"
					className="bg-muted/50 text-[10px] font-mono border-border/50 px-1.5 py-0 h-5"
				>
					<span className="opacity-60 mr-1">{key}:</span>
					{value}
				</Badge>
			))}
			{extraCount > 0 && (
				<Badge
					variant="outline"
					className="text-[10px] px-1.5 py-0 h-5 text-muted-foreground"
				>
					+{extraCount}
				</Badge>
			)}
		</div>
	);
}

// =============================================================================
// Main Component
// =============================================================================

export function InventoryTable({
	resources,
	isLoading,
	pagination,
	onPageChange,
	onRowClick,
	hasActiveFilters,
}: InventoryTableProps) {
	if (isLoading) {
		return <TableSkeleton />;
	}

	if (pagination.total === 0) {
		return <EmptyState hasActiveFilters={hasActiveFilters} />;
	}

	const startItem = (pagination.page - 1) * pagination.size + 1;
	const endItem = Math.min(pagination.page * pagination.size, pagination.total);

	return (
		<Card className="flex flex-col border-border/50 bg-card overflow-hidden shadow-sm">
			<div className="overflow-x-auto">
				<Table>
					<TableHeader className="bg-muted/20">
						<TableRow className="hover:bg-transparent border-b border-border/50">
							<TableHead className="w-[350px]">Platform & Name</TableHead>
							<TableHead className="w-[140px]">Sensitivity</TableHead>
							<TableHead className="w-[160px]">Owner</TableHead>
							<TableHead>Tags</TableHead>
							<TableHead className="w-[60px]"></TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{resources.map((resource) => {
							const displayName =
								resource.name ||
								resource.urn.split(":").pop() ||
								"Unknown Resource";
							const owner = resource.attributes?.owner || "Unassigned";

							return (
								<TableRow
									key={resource.id}
									className="group cursor-pointer hover:bg-muted/30 transition-colors border-border/40"
									onClick={() => onRowClick(resource)}
								>
									{/* 1. Platform & Name */}
									<TableCell>
										<div className="flex items-center gap-3">
											<div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted/50 border border-border/50">
												<PlatformIcon platform={resource.platform} />
											</div>
											<div className="flex flex-col min-w-0">
												<span className="font-semibold text-sm text-foreground truncate">
													{displayName}
												</span>
												<span className="text-[10px] text-muted-foreground font-mono truncate max-w-[280px]">
													{resource.urn}
												</span>
											</div>
										</div>
									</TableCell>

									{/* 2. Sensitivity */}
									<TableCell>
										<SensitivityBadge resource={resource} />
									</TableCell>

									{/* 3. Owner */}
									<TableCell>
										<span
											className={cn(
												"text-xs truncate max-w-[140px] block",
												owner === "Unassigned"
													? "text-muted-foreground italic"
													: "font-medium text-foreground/90",
											)}
										>
											{owner}
										</span>
									</TableCell>

									{/* 4. Tags */}
									<TableCell>
										<FormatTags tags={resource.attributes?.tags} />
									</TableCell>

									{/* 5. Actions */}
									<TableCell>
										<div onClick={(e) => e.stopPropagation()}>
											<DropdownMenu>
												<DropdownMenuTrigger asChild>
													<Button
														variant="ghost"
														size="icon"
														className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
													>
														<MoreHorizontal className="h-4 w-4 text-muted-foreground" />
														<span className="sr-only">Actions</span>
													</Button>
												</DropdownMenuTrigger>
												<DropdownMenuContent align="end" className="w-48">
													<DropdownMenuLabel>
														Resource Actions
													</DropdownMenuLabel>
													<DropdownMenuItem
														onClick={() => onRowClick(resource)}
													>
														<Eye className="mr-2 h-4 w-4" />
														View Details
													</DropdownMenuItem>
													<DropdownMenuItem
														onClick={() =>
															navigator.clipboard.writeText(resource.urn)
														}
													>
														<Copy className="mr-2 h-4 w-4" />
														Copy URN
													</DropdownMenuItem>
													<DropdownMenuSeparator />
													<DropdownMenuItem>
														<FileJson className="mr-2 h-4 w-4" />
														View Raw JSON
													</DropdownMenuItem>
												</DropdownMenuContent>
											</DropdownMenu>
										</div>
									</TableCell>
								</TableRow>
							);
						})}
					</TableBody>
				</Table>
			</div>

			{/* Pagination Footer */}
			<div className="flex items-center justify-between px-6 py-4 border-t border-border/50 bg-muted/10">
				<div className="text-xs text-muted-foreground">
					Showing{" "}
					<span className="font-medium text-foreground">{startItem}</span> to{" "}
					<span className="font-medium text-foreground">{endItem}</span> of{" "}
					<span className="font-medium text-foreground">
						{pagination.total}
					</span>{" "}
					resources
				</div>
				<div className="flex items-center gap-2">
					<Button
						variant="outline"
						size="sm"
						className="h-8 w-8 p-0"
						onClick={() => onPageChange(pagination.page - 1)}
						disabled={pagination.page <= 1}
					>
						<ChevronLeft className="h-4 w-4" />
					</Button>
					<span className="text-xs font-medium text-muted-foreground px-2">
						Page {pagination.page} of {pagination.pages}
					</span>
					<Button
						variant="outline"
						size="sm"
						className="h-8 w-8 p-0"
						onClick={() => onPageChange(pagination.page + 1)}
						disabled={pagination.page >= pagination.pages}
					>
						<ChevronRight className="h-4 w-4" />
					</Button>
				</div>
			</div>
		</Card>
	);
}

// =============================================================================
// Skeletons & Empty States
// =============================================================================

function TableSkeleton() {
	return (
		<Card className="border-border/50 bg-card overflow-hidden">
			<div className="border-b border-border/50 p-4 bg-muted/20">
				<div className="flex gap-4">
					<Skeleton className="h-4 w-[250px]" />
					<Skeleton className="h-4 w-[100px]" />
					<Skeleton className="h-4 w-[100px]" />
					<Skeleton className="h-4 w-[200px]" />
				</div>
			</div>
			<div className="divide-y divide-border/30">
				{Array.from({ length: 5 }).map((_, i) => (
					<div key={i} className="flex items-center gap-4 p-4">
						<Skeleton className="h-9 w-9 rounded-md shrink-0" />
						<div className="space-y-2 w-[250px]">
							<Skeleton className="h-4 w-[200px]" />
							<Skeleton className="h-3 w-[250px]" />
						</div>
						<Skeleton className="h-5 w-20 rounded-full" />
						<Skeleton className="h-4 w-24" />
						<div className="flex gap-2 flex-1">
							<Skeleton className="h-5 w-16 rounded-full" />
							<Skeleton className="h-5 w-20 rounded-full" />
						</div>
					</div>
				))}
			</div>
		</Card>
	);
}

function EmptyState({ hasActiveFilters }: { hasActiveFilters: boolean }) {
	if (hasActiveFilters) {
		return (
			<Card className="flex flex-col items-center justify-center py-24 text-center border-dashed border-2 border-border/50 bg-card/50">
				<Database className="h-10 w-10 text-muted-foreground/30 mb-4" />
				<h3 className="text-lg font-medium text-foreground">
					No matches found
				</h3>
				<p className="text-sm text-muted-foreground mt-1 max-w-sm">
					No resources match your current filters. Try adjusting your search
					query or clearing filters.
				</p>
			</Card>
		);
	}

	// The "Zero State" (Onboarding)
	return (
		<Card className="flex flex-col items-center justify-center py-20 text-center border-dashed border-2 border-border/50 bg-card">
			<div className="h-16 w-16 rounded-full bg-indigo-500/10 flex items-center justify-center mb-6">
				<Database className="h-8 w-8 text-indigo-400" />
			</div>
			<h3 className="text-xl font-semibold tracking-tight text-foreground">
				Your Data Map is Empty
			</h3>
			<p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto leading-relaxed">
				Connect your data platforms to start mapping resources and enforcing
				policies. Ambyte uses CLI connectors to securely sync metadata without
				accessing your raw data.
			</p>

			<div className="mt-8 rounded-xl border border-zinc-800 bg-[#0D0D0D] shadow-2xl overflow-hidden w-full max-w-lg text-left">
				<div className="flex items-center px-4 py-2 border-b border-zinc-800 bg-zinc-900/80">
					<TerminalSquare className="h-4 w-4 text-zinc-500 mr-2" />
					<span className="text-xs font-mono text-zinc-400">
						Sync Databricks Inventory
					</span>
				</div>
				<div className="p-4 font-mono text-[12px] leading-relaxed">
					<div className="text-zinc-500 mb-1"># 1. Install the connector</div>
					<div className="text-zinc-300 mb-4">
						pip install ambyte-databricks
					</div>

					<div className="text-zinc-500 mb-1">
						# 2. Sync metadata to the Control Plane
					</div>
					<div className="flex flex-wrap gap-x-1">
						<span className="text-indigo-400">ambyte-databricks</span>
						<span className="text-zinc-300">inventory sync</span>
					</div>
				</div>
			</div>
		</Card>
	);
}
