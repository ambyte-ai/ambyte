"use client";

import { Database, Server, ShieldAlert, Tags } from "lucide-react";
import { useMemo } from "react";
import { KpiCard } from "@/components/dashboard/kpi-card";
import type { Resource } from "@/hooks/use-inventory";
import { useRiskResources } from "@/hooks/use-risk-resources";

interface InventoryKpisProps {
	totalResources: number;
	currentResources: Resource[];
	isLoading: boolean;
}

export function InventoryKpis({
	totalResources,
	currentResources,
	isLoading,
}: InventoryKpisProps) {
	// Fetch high-risk resources independently (global scope, limit 50 for a solid count)
	const { resources: riskResources, isLoading: isLoadingRisks } =
		useRiskResources(50);

	// Calculate Active Platforms (based on the current view/page)
	const activePlatforms = useMemo(() => {
		if (!currentResources.length) return [];
		const platforms = new Set(currentResources.map((r) => r.platform));
		return Array.from(platforms);
	}, [currentResources]);

	// Calculate Tag Coverage (based on the current view/page)
	const tagCoverage = useMemo(() => {
		if (!currentResources.length) return 0;
		const taggedCount = currentResources.filter(
			(r) => Object.keys(r.attributes?.tags || {}).length > 0,
		).length;
		return Math.round((taggedCount / currentResources.length) * 100);
	}, [currentResources]);

	const formatPlatformsList = (platforms: string[]) => {
		if (platforms.length === 0) return "None";
		if (platforms.length <= 2) return platforms.join(", ");
		return `${platforms.slice(0, 2).join(", ")} +${platforms.length - 2}`;
	};

	const riskCount = riskResources?.length || 0;
	const isDataLoading = isLoading || isLoadingRisks;

	return (
		<div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
			{/* KPI 1: Total Assets */}
			<KpiCard
				title="Total Assets"
				value={totalResources}
				subtext="Tracked in inventory"
				icon={Database}
				status="default"
				isLoading={isDataLoading}
			/>

			{/* KPI 2: High-Risk Assets */}
			<KpiCard
				title="High-Risk Assets"
				value={riskCount}
				subtext="Confidential or Restricted"
				icon={ShieldAlert}
				// Turn red if there are high-risk assets, otherwise green/default
				status={riskCount > 0 ? "error" : "success"}
				isLoading={isDataLoading}
				className={riskCount > 0 ? "border-rose-500/30 bg-rose-500/5" : ""}
			/>

			{/* KPI 3: Active Platforms */}
			<KpiCard
				title="Active Platforms"
				value={activePlatforms.length}
				subtext={formatPlatformsList(activePlatforms)}
				icon={Server}
				status="default"
				isLoading={isDataLoading}
			/>

			{/* KPI 4: Tag Coverage */}
			<KpiCard
				title="Tag Coverage"
				value={`${tagCoverage}%`}
				subtext="Assets with metadata"
				icon={Tags}
				// Warning if tag coverage drops below 100%
				status={tagCoverage === 100 ? "success" : "warning"}
				isLoading={isDataLoading}
			/>
		</div>
	);
}
