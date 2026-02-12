"use client";

import {
	Activity,
	Calendar,
	CheckCircle2,
	Loader2,
	Plus,
	Server,
	Shield,
	ShieldCheck,
	UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { IngestionQueue } from "@/components/dashboard/ingestion-queue";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { ReasonChart } from "@/components/dashboard/reason-chart";
import { RiskList } from "@/components/dashboard/risk-list";
import { TrafficChart } from "@/components/dashboard/traffic-chart";
import { ViolationStream } from "@/components/dashboard/violation-stream";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { useProject } from "@/context/project-context";
import { useDashboardStats } from "@/hooks/use-ambyte-stats";

// Time range mapping
const TIME_RANGES = {
	"24h": 24,
	"7d": 168,
	"30d": 720,
};

type TimeRangeKey = keyof typeof TIME_RANGES;

export default function DashboardPage() {
	const { projectId, isLoading: isProjectLoading } = useProject();
	const [timeRange, setTimeRange] = useState<TimeRangeKey>("24h");

	const {
		stats,
		isLoading: isStatsLoading,
		isError,
	} = useDashboardStats(TIME_RANGES[timeRange]);

	const isLoading = isProjectLoading || isStatsLoading;

	// ---------------------------------------------------------------------------
	// Empty State / Onboarding View
	// ---------------------------------------------------------------------------
	// Show this if data loads but implies a fresh project (0 resources, 0 obligations)
	if (
		!isLoading &&
		stats &&
		stats.kpi.active_obligations === 0 &&
		stats.kpi.protected_resources === 0
	) {
		return (
			<div className="flex h-[calc(100vh-100px)] w-full flex-col items-center justify-center space-y-8">
				<div className="text-center space-y-2">
					<div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-4">
						<Shield className="h-8 w-8 text-primary" />
					</div>
					<h2 className="text-2xl font-bold tracking-tight">
						Welcome to Ambyte
					</h2>
					<p className="text-muted-foreground max-w-md mx-auto">
						Your workspace is ready. Define your first policy or connect a data
						source to get started.
					</p>
				</div>

				<div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl">
					<Link href="/ingest" className="w-full group">
						<Card className="h-full border-border/50 bg-card/50 hover:bg-card hover:border-primary/50 transition-all cursor-pointer group-hover:shadow-md">
							<CardContent className="flex flex-col items-center justify-center p-8 text-center space-y-4">
								<div className="p-3 rounded-full bg-indigo-500/10 text-indigo-400 group-hover:bg-indigo-500/20 group-hover:scale-110 transition-all">
									<UploadCloud className="h-8 w-8" />
								</div>
								<div className="space-y-1">
									<h3 className="font-semibold text-foreground">
										Upload Contract
									</h3>
									<p className="text-sm text-muted-foreground">
										Ingest a PDF (DPA/MSA) to auto-generate policies.
									</p>
								</div>
							</CardContent>
						</Card>
					</Link>

					<Link href="/resources" className="w-full group">
						<Card className="h-full border-border/50 bg-card/50 hover:bg-card hover:border-primary/50 transition-all cursor-pointer group-hover:shadow-md">
							<CardContent className="flex flex-col items-center justify-center p-8 text-center space-y-4">
								<div className="p-3 rounded-full bg-emerald-500/10 text-emerald-400 group-hover:bg-emerald-500/20 group-hover:scale-110 transition-all">
									<Server className="h-8 w-8" />
								</div>
								<div className="space-y-1">
									<h3 className="font-semibold text-foreground">
										Connect Data Source
									</h3>
									<p className="text-sm text-muted-foreground">
										Register Snowflake, Databricks, or S3 resources.
									</p>
								</div>
							</CardContent>
						</Card>
					</Link>
				</div>
			</div>
		);
	}

	// ---------------------------------------------------------------------------
	// Main Dashboard Grid
	// ---------------------------------------------------------------------------
	return (
		<div className="space-y-6 animate-in fade-in duration-500">
			{/* Dashboard Header */}
			<div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
				<div>
					<h2 className="text-2xl font-bold tracking-tight">Overview</h2>
					<p className="text-sm text-muted-foreground">
						Governance posture and real-time activity.
					</p>
				</div>
				<div className="flex items-center gap-2">
					<Select
						value={timeRange}
						onValueChange={(v) => setTimeRange(v as TimeRangeKey)}
						disabled={isLoading}
					>
						<SelectTrigger className="w-[140px] h-9 text-xs">
							<Calendar className="mr-2 h-3.5 w-3.5 opacity-70" />
							<SelectValue placeholder="Time Range" />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="24h">Last 24 Hours</SelectItem>
							<SelectItem value="7d">Last 7 Days</SelectItem>
							<SelectItem value="30d">Last 30 Days</SelectItem>
						</SelectContent>
					</Select>
					<Button variant="default" size="sm" className="h-9 gap-2">
						<Plus className="h-4 w-4" />
						New Policy
					</Button>
				</div>
			</div>

			{/* 
        GRID LAYOUT 
        4 columns on large screens, collapsing to 1 on mobile.
      */}
			<div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
				{/* ========================== ROW 1: THE PULSE ========================== */}

				{/* KPI 1: Enforcement Rate */}
				<KpiCard
					title="Enforcement Rate"
					value={
						stats
							? `${stats.kpi.enforcement_rate_24h}%`
							: isLoading
								? "..."
								: "0%"
					}
					subtext="Allowed Requests"
					status={
						(stats?.kpi.enforcement_rate_24h || 100) < 90
							? "warning"
							: "success"
					}
					icon={Activity}
					isLoading={isLoading}
				/>

				{/* KPI 2: Active Obligations */}
				<KpiCard
					title="Active Obligations"
					value={stats?.kpi.active_obligations ?? 0}
					subtext="Policies Enforced"
					icon={ShieldCheck}
					status="default"
					isLoading={isLoading}
				/>

				{/* KPI 3: Protected Resources */}
				<KpiCard
					title="Protected Resources"
					value={stats?.kpi.protected_resources ?? 0}
					subtext="Inventory Coverage"
					icon={Server}
					status="default"
					isLoading={isLoading}
				/>

				{/* KPI 4: Pending Ingestions */}
				<KpiCard
					title="Ingestion Queue"
					value={stats?.kpi.pending_ingestions ?? 0}
					subtext={
						stats?.kpi.pending_ingestions === 0
							? "All caught up"
							: "Processing..."
					}
					icon={stats?.kpi.pending_ingestions === 0 ? CheckCircle2 : Loader2}
					status={stats?.kpi.pending_ingestions === 0 ? "success" : "warning"}
					isLoading={isLoading}
					className={
						(stats?.kpi.pending_ingestions ?? 0 > 0)
							? "border-amber-500/30 bg-amber-500/5"
							: ""
					}
				/>

				{/* ========================== ROW 2: THE TIMELINE ========================== */}

				{/* Main Traffic Chart (Spans 3 cols) */}
				<div className="md:col-span-2 lg:col-span-3">
					<TrafficChart
						data={stats?.traffic_series}
						isLoading={isLoading}
						className="h-full min-h-[350px]"
					/>
				</div>

				{/* Denial Reason Donut (Spans 1 col) */}
				<div className="md:col-span-2 lg:col-span-1">
					<ReasonChart
						data={stats?.top_deny_reasons}
						isLoading={isLoading}
						className="h-full min-h-[350px]"
					/>
				</div>

				{/* ========================== ROW 3: TRIAGE LISTS ========================== */}

				{/* Recent Violations (Spans 2 cols) */}
				<div className="md:col-span-2">
					<ViolationStream
						data={stats?.recent_blocks}
						isLoading={isLoading}
						className="h-full min-h-[400px]"
					/>
				</div>

				{/* At-Risk Resources (Spans 2 cols) */}
				<div className="md:col-span-2">
					<RiskList className="h-full min-h-[400px]" />
				</div>

				{/* ========================== ROW 4: INGESTION ========================== */}

				{/* Live Ingestion Queue Table */}
				<IngestionQueue className="col-span-full" />
			</div>
		</div>
	);
}
