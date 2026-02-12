import { useState } from "react";
import { Badge } from "@/components/ui/badge";
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
import { cn } from "@/lib/utils";
import type { Obligation } from "@/types/obligation";
import { ConstraintIcon } from "./constraint-icon";
import { EnforcementBadge } from "./enforcement-badge";
import { ObligationDrawer } from "./obligation-drawer";

interface ObligationsTableProps {
	obligations: Obligation[];
}

export function ObligationsTable({ obligations }: ObligationsTableProps) {
	const [selectedObligation, setSelectedObligation] =
		useState<Obligation | null>(null);

	// Helper to determine status color (mocked for now as we don't have a status field)
	// potentially could use dates or enforcement level to drive this
	const getStatusColor = (_: Obligation) => "bg-emerald-500";

	return (
		<>
			<div className="rounded-md border bg-card">
				<Table>
					<TableHeader>
						<TableRow className="hover:bg-transparent">
							<TableHead className="w-[50px]">Status</TableHead>
							<TableHead className="w-[250px]">Name</TableHead>
							<TableHead className="w-[100px]">Type</TableHead>
							<TableHead className="w-[150px]">Enforcement</TableHead>
							<TableHead className="text-right">Source</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{obligations.length === 0 ? (
							<TableRow>
								<TableCell
									colSpan={5}
									className="h-24 text-center text-muted-foreground"
								>
									No obligations found.
								</TableCell>
							</TableRow>
						) : (
							obligations.map((ob) => (
								<TableRow
									key={ob.id}
									className="cursor-pointer hover:bg-muted/50"
									onClick={() => setSelectedObligation(ob)}
								>
									<TableCell>
										<TooltipProvider>
											<Tooltip>
												<TooltipTrigger>
													<div
														className={cn(
															"h-2.5 w-2.5 rounded-full",
															getStatusColor(ob),
														)}
													/>
												</TooltipTrigger>
												<TooltipContent>
													<p>Active</p>
												</TooltipContent>
											</Tooltip>
										</TooltipProvider>
									</TableCell>
									<TableCell>
										<div className="flex flex-col gap-0.5">
											<span className="font-medium line-clamp-1">
												{ob.title}
											</span>
											<span className="text-xs text-muted-foreground font-mono truncate max-w-[200px]">
												{ob.id}
											</span>
										</div>
									</TableCell>
									<TableCell>
										<ConstraintIcon obligation={ob} />
									</TableCell>
									<TableCell>
										<EnforcementBadge
											level={ob.enforcement_level}
											showIcon={true}
											className="bg-transparent border-transparent px-0 font-normal hover:bg-transparent text-foreground"
										/>
									</TableCell>
									<TableCell className="text-right">
										<Badge
											variant="outline"
											className="font-mono text-[10px] text-muted-foreground"
										>
											{ob.provenance.source_id}
										</Badge>
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
