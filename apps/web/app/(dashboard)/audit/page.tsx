"use client";

import { RefreshCw, ScrollText } from "lucide-react";
import { useState } from "react";

import { AuditDrawer } from "@/components/audit/audit-drawer";
import { AuditKpis } from "@/components/audit/audit-kpis";
import { AuditTable } from "@/components/audit/audit-table";
import { AuditToolbar } from "@/components/audit/audit-toolbar";
import { Button } from "@/components/ui/button";
import { useAuditLogs } from "@/hooks/use-audit-logs";
import { cn } from "@/lib/utils";
import type { AuditLog, Decision } from "@/types/audit";

export default function AuditPage() {
	// =========================================================================
	// State Management (Controller Pattern)
	// =========================================================================

	// Filter State
	const [searchQuery, setSearchQuery] = useState("");
	const [decisionFilter, setDecisionFilter] = useState<Decision | "ALL">("ALL");
	const [actionFilter, setActionFilter] = useState("all");
	const [isLiveTail, setIsLiveTail] = useState(false);

	// Drawer State
	const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

	// =========================================================================
	// Data Fetching
	// =========================================================================

	const { logs, isLoading, isValidating, refresh } = useAuditLogs(
		{
			decision: decisionFilter,
			actorId:
				searchQuery.includes("@") || searchQuery.includes("_")
					? searchQuery
					: undefined,
			resourceUrn: searchQuery.includes(":") ? searchQuery : undefined,
		},
		isLiveTail,
	);

	// =========================================================================
	// Client-Side Search (omni-search across actor, resource, hash)
	// The hook already handles decision filtering.
	// We additionally filter by free-text search across multiple fields.
	// =========================================================================

	const filteredLogs = searchQuery
		? logs.filter((log) => {
				const q = searchQuery.toLowerCase();
				return (
					log.actor_id.toLowerCase().includes(q) ||
					log.resource_urn.toLowerCase().includes(q) ||
					log.entry_hash.toLowerCase().includes(q) ||
					log.action.toLowerCase().includes(q) ||
					(log.reason_trace?.decision_reason || "").toLowerCase().includes(q)
				);
			})
		: logs;

	// =========================================================================
	// Render
	// =========================================================================

	return (
		<div className="flex h-full flex-col gap-6 animate-in fade-in duration-500">
			{/* A. HEADER REGION */}
			<div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
				<div>
					<div className="flex items-center gap-2">
						<ScrollText className="h-6 w-6 text-primary" />
						<h1 className="text-2xl font-bold tracking-tight">Audit Ledger</h1>
					</div>
					<p className="text-sm text-muted-foreground mt-1">
						Cryptographically sealed record of all policy evaluations and data
						access events.
					</p>
				</div>
				<div className="flex items-center gap-2">
					<Button
						variant="outline"
						size="sm"
						className="gap-2 shadow-sm"
						onClick={() => refresh()}
						disabled={isValidating}
					>
						<RefreshCw
							className={cn(
								"h-4 w-4",
								isValidating && "animate-spin text-primary",
							)}
						/>
						Refresh
					</Button>
				</div>
			</div>

			{/* B. KPIs (The "Pulse") */}
			<AuditKpis logs={logs} isLoading={isLoading && !isValidating} />

			{/* C. TOOLBAR (Search, Decision Toggle, Live Tail) */}
			<AuditToolbar
				searchQuery={searchQuery}
				onSearchChange={setSearchQuery}
				decisionFilter={decisionFilter}
				onDecisionChange={setDecisionFilter}
				isLiveTail={isLiveTail}
				onLiveTailChange={setIsLiveTail}
				actionFilter={actionFilter}
				onActionChange={setActionFilter}
			/>

			{/* D. THE AUDIT LEDGER (Data Table) */}
			<div className="flex-1">
				<AuditTable
					logs={filteredLogs}
					isLoading={isLoading && !isValidating}
					onRowClick={setSelectedLog}
				/>
			</div>

			{/* E. THE DEEP-DIVE INSPECTOR DRAWER */}
			<AuditDrawer
				log={selectedLog}
				open={!!selectedLog}
				onOpenChange={(open) => !open && setSelectedLog(null)}
			/>
		</div>
	);
}
