import { Copy, Eye, FileJson, MoreHorizontal } from "lucide-react";
import { useState } from "react";

import { ConstraintIcon } from "@/components/obligations/constraint-icon";
import { EnforcementBadge } from "@/components/obligations/enforcement-badge";
import { ObligationDrawer } from "@/components/obligations/obligation-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Obligation } from "@/types/obligation";

interface ObligationsTableProps {
	obligations: Obligation[];
	isLoading?: boolean;
}

export function ObligationsTable({
	obligations,
	isLoading,
}: ObligationsTableProps) {
	const [selectedObligation, setSelectedObligation] =
		useState<Obligation | null>(null);

	// Helper: Format targeting scope summary (e.g. "tag:sensitivity=high")
	const formatTargeting = (ob: Obligation) => {
		const tags = ob.target.match_tags;
		const patterns = ob.target.include_patterns;

		if (tags && Object.keys(tags).length > 0) {
			const firstKey = Object.keys(tags)[0];
			const count = Object.keys(tags).length;
			return (
				<div className="flex items-center gap-1.5">
					<Badge
						variant="secondary"
						className="bg-muted/50 text-[10px] font-mono border-border px-1.5 py-0 h-5"
					>
						tag:{firstKey}={tags[firstKey]}
					</Badge>
					{count > 1 && (
						<span className="text-[10px] text-muted-foreground">
							+{count - 1}
						</span>
					)}
				</div>
			);
		}

		if (patterns && patterns.length > 0) {
			return (
				<span className="font-mono text-[10px] text-muted-foreground truncate max-w-[150px] block">
					{patterns[0]} {patterns.length > 1 && `(+${patterns.length - 1})`}
				</span>
			);
		}

		return <span className="text-[10px] text-muted-foreground/50">Global</span>;
	};

	if (isLoading) {
		return <TableSkeleton />;
	}

	return (
		<>
			<div className="rounded-md">
				<Table>
					<TableHeader>
						<TableRow className="hover:bg-transparent border-b border-border/50">
							<TableHead className="w-[50px]">Status</TableHead>
							<TableHead className="w-[300px]">Policy Name</TableHead>
							<TableHead className="w-[80px]">Type</TableHead>
							<TableHead className="w-[140px]">Enforcement</TableHead>
							<TableHead className="w-[180px]">Source</TableHead>
							<TableHead>Targeting</TableHead>
							<TableHead className="w-[60px]"></TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{obligations.length === 0 ? (
							<TableRow>
								<TableCell
									colSpan={7}
									className="h-32 text-center text-muted-foreground"
								>
									No obligations found matching your criteria.
								</TableCell>
							</TableRow>
						) : (
							obligations.map((ob) => (
								<TableRow
									key={ob.id}
									className="group cursor-pointer hover:bg-muted/30 transition-colors border-border/40"
									onClick={() => setSelectedObligation(ob)}
								>
									{/* 1. Status Column */}
									<TableCell>
										<TooltipProvider>
											<Tooltip>
												<TooltipTrigger onClick={(e) => e.stopPropagation()}>
													<div className="flex items-center justify-center">
														{/* TODO: Implement Active/Inactive toggle logic via API */}
														<div className="h-2.5 w-2.5 rounded-full bg-emerald-500 ring-4 ring-emerald-500/10" />
													</div>
												</TooltipTrigger>
												<TooltipContent>
													<p>Status: Active</p>
												</TooltipContent>
											</Tooltip>
										</TooltipProvider>
									</TableCell>

									{/* 2. Policy Name */}
									<TableCell>
										<div className="flex flex-col gap-0.5">
											<span className="font-semibold text-sm text-foreground">
												{ob.title}
											</span>
											<span className="text-[11px] text-muted-foreground font-mono truncate max-w-[280px]">
												{ob.id}
											</span>
										</div>
									</TableCell>

									{/* 3. Type Icon */}
									<TableCell>
										<ConstraintIcon obligation={ob} />
									</TableCell>

									{/* 4. Enforcement Badge */}
									<TableCell>
										<EnforcementBadge level={ob.enforcement_level} />
									</TableCell>

									{/* 5. Source (Provenance) */}
									<TableCell>
										<div
											className="flex flex-col gap-0.5 max-w-[160px]"
											title={ob.provenance.source_id}
										>
											<span className="text-xs font-medium truncate">
												{ob.provenance.source_id}
											</span>
											<span className="text-[10px] text-muted-foreground truncate">
												{ob.provenance.section_reference || "Whole Doc"}
											</span>
										</div>
									</TableCell>

									{/* 6. Targeting (Scope) */}
									<TableCell>{formatTargeting(ob)}</TableCell>

									{/* 7. Actions */}
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
												<DropdownMenuContent align="end">
													<DropdownMenuLabel>Actions</DropdownMenuLabel>
													<DropdownMenuItem
														onClick={() => setSelectedObligation(ob)}
													>
														<Eye className="mr-2 h-4 w-4" />
														View Details
													</DropdownMenuItem>
													<DropdownMenuItem
														onClick={() => navigator.clipboard.writeText(ob.id)}
													>
														<Copy className="mr-2 h-4 w-4" />
														Copy ID
													</DropdownMenuItem>
													<DropdownMenuSeparator />
													<DropdownMenuItem>
														<FileJson className="mr-2 h-4 w-4" />
														View JSON
													</DropdownMenuItem>
												</DropdownMenuContent>
											</DropdownMenu>
										</div>
									</TableCell>
								</TableRow>
							))
						)}
					</TableBody>
				</Table>
			</div>

			<ObligationDrawer
				obligation={selectedObligation}
				open={!!selectedObligation}
				onOpenChange={(open) => !open && setSelectedObligation(null)}
			/>
		</>
	);
}

function TableSkeleton() {
	return (
		<div className="rounded-md border bg-card">
			<div className="border-b p-4">
				<div className="flex gap-4">
					<Skeleton className="h-4 w-[50px]" />
					<Skeleton className="h-4 w-[250px]" />
					<Skeleton className="h-4 w-[100px]" />
					<Skeleton className="h-4 w-[100px]" />
				</div>
			</div>
			<div className="divide-y divide-border/30">
				{Array.from({ length: 5 }).map((_, i) => (
					<div key={i} className="flex items-center gap-4 p-4">
						<Skeleton className="h-8 w-8 rounded-full" />
						<div className="space-y-2 flex-1">
							<Skeleton className="h-4 w-[200px]" />
							<Skeleton className="h-3 w-[150px]" />
						</div>
						<Skeleton className="h-6 w-20" />
						<Skeleton className="h-6 w-32" />
					</div>
				))}
			</div>
		</div>
	);
}
