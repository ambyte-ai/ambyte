"use client";

import { Activity, Lock, ShieldAlert, Timer, Users } from "lucide-react";
import { useMemo } from "react";
import { KpiCard } from "@/components/dashboard/kpi-card";
import type { AuditLog } from "@/types/audit";

interface AuditKpisProps {
	logs: AuditLog[];
	isLoading: boolean;
}

export function AuditKpis({ logs, isLoading }: AuditKpisProps) {
	// -------------------------------------------------------------------------
	// Compute Metrics
	// We memoize these so we don't recalculate on every render, especially
	// important when "Live Tail" polling is active and pushing new arrays.
	// -------------------------------------------------------------------------
	const metrics = useMemo(() => {
		if (!logs || logs.length === 0) {
			return {
				total: 0,
				denialRate: 0,
				bufferedCount: 0,
				sealedCount: 0,
				uniqueActors: 0,
			};
		}

		const total = logs.length;

		let deniedCount = 0;
		let bufferedCount = 0;
		const actors = new Set<string>();

		for (const log of logs) {
			// Count Denials (including DRY_RUN_DENY)
			if (log.decision.includes("DENY")) {
				deniedCount++;
			}

			// Count Pending Seals (Buffered in Redis, not yet in a Postgres Block)
			if (log.block_id === null) {
				bufferedCount++;
			}

			// Track Unique Actors
			if (log.actor_id) {
				actors.add(log.actor_id);
			}
		}

		const denialRate = Math.round((deniedCount / total) * 100);

		return {
			total,
			denialRate,
			bufferedCount,
			sealedCount: total - bufferedCount,
			uniqueActors: actors.size,
		};
	}, [logs]);

	// -------------------------------------------------------------------------
	// Render
	// -------------------------------------------------------------------------
	return (
		<div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
			{/* KPI 1: Total Events in View */}
			<KpiCard
				title="Events Tracked"
				value={metrics.total}
				subtext="In current view"
				icon={Activity}
				status="default"
				isLoading={isLoading}
			/>

			{/* KPI 2: Denial Rate */}
			<KpiCard
				title="Denial Rate"
				value={`${metrics.denialRate}%`}
				subtext="Access blocked"
				icon={ShieldAlert}
				// Highlight if denial rate is unusually high (e.g., > 20%)
				status={metrics.denialRate > 20 ? "warning" : "default"}
				isLoading={isLoading}
			/>

			{/* KPI 3: Cryptographic Seal Status */}
			<KpiCard
				title="Pending Seal"
				value={metrics.bufferedCount}
				subtext={
					metrics.bufferedCount === 0
						? `${metrics.sealedCount} logs sealed`
						: "Awaiting cryptographic block"
				}
				icon={metrics.bufferedCount > 0 ? Timer : Lock}
				// Show warning if logs are piling up in the buffer, success if everything is sealed
				status={metrics.bufferedCount > 0 ? "warning" : "success"}
				isLoading={isLoading}
				className={
					metrics.bufferedCount > 0 ? "border-amber-500/30 bg-amber-500/5" : ""
				}
			/>

			{/* KPI 4: Active Entities */}
			<KpiCard
				title="Active Actors"
				value={metrics.uniqueActors}
				subtext="Unique identities/services"
				icon={Users}
				status="default"
				isLoading={isLoading}
			/>
		</div>
	);
}
