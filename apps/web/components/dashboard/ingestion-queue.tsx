"use client";

import {
	AlertCircle,
	CheckCircle2,
	ChevronRight,
	FileText,
	Loader2,
	RefreshCw,
	Timer,
} from "lucide-react";
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
import {
	type IngestJob,
	type IngestStatus,
	useIngestJobs,
} from "@/hooks/use-ingest-jobs";
import { cn } from "@/lib/utils";

interface IngestionQueueProps {
	className?: string;
	onJobClick?: (job: IngestJob) => void;
}

// -----------------------------------------------------------------------------
// UI Helpers
// -----------------------------------------------------------------------------

const STATUS_CONFIG: Record<
	IngestStatus,
	{ label: string; color: string; icon: any; animate?: boolean }
> = {
	QUEUED: {
		label: "Queued",
		color: "bg-zinc-500/10 text-zinc-500 border-zinc-500/20",
		icon: Timer,
	},
	PARSING: {
		label: "Parsing PDF",
		color: "bg-blue-500/10 text-blue-500 border-blue-500/20",
		icon: Loader2,
		animate: true,
	},
	CHUNKING: {
		label: "Chunking",
		color: "bg-blue-500/10 text-blue-500 border-blue-500/20",
		icon: Loader2,
		animate: true,
	},
	EMBEDDING: {
		label: "Embedding",
		color: "bg-indigo-500/10 text-indigo-500 border-indigo-500/20",
		icon: Loader2,
		animate: true,
	},
	DEFINING: {
		label: "Extracting Definitions",
		color: "bg-violet-500/10 text-violet-500 border-violet-500/20",
		icon: Loader2,
		animate: true,
	},
	EXTRACTION: {
		label: "Analyzing Rules",
		color: "bg-violet-500/10 text-violet-500 border-violet-500/20",
		icon: Loader2,
		animate: true,
	},
	MERGING: {
		label: "Finalizing",
		color: "bg-purple-500/10 text-purple-500 border-purple-500/20",
		icon: Loader2,
		animate: true,
	},
	SYNCING: {
		label: "Syncing Cloud",
		color: "bg-purple-500/10 text-purple-500 border-purple-500/20",
		icon: Loader2,
		animate: true,
	},
	COMPLETED: {
		label: "Complete",
		color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
		icon: CheckCircle2,
	},
	FAILED: {
		label: "Failed",
		color: "bg-rose-500/10 text-rose-500 border-rose-500/20",
		icon: AlertCircle,
	},
};

export function IngestionQueue({ className, onJobClick }: IngestionQueueProps) {
	const { jobs, isLoading, refresh } = useIngestJobs(10);

	// Filter out jobs that might be corrupted or missing IDs
	const validJobs = jobs.filter((j) => j.job_id);

	if (isLoading) {
		return <QueueSkeleton className={className} />;
	}

	return (
		<Card className={cn("border-border/50", className)}>
			<CardHeader className="flex flex-row items-center justify-between py-4">
				<div className="space-y-1">
					<CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground/70 flex items-center gap-2">
						<FileText className="h-4 w-4" />
						Document Processing Queue
					</CardTitle>
					<CardDescription className="text-xs">
						Real-time status of contract ingestion pipelines.
					</CardDescription>
				</div>
				<Button
					variant="ghost"
					size="sm"
					onClick={() => refresh()}
					className="h-8 w-8 p-0"
				>
					<RefreshCw className="h-4 w-4 opacity-70" />
				</Button>
			</CardHeader>
			<CardContent className="p-0">
				{validJobs.length === 0 ? (
					<div className="flex h-32 flex-col items-center justify-center text-center text-sm text-muted-foreground bg-muted/5 border-t border-border/50">
						<FileText className="h-8 w-8 mb-2 opacity-20" />
						<p>No active jobs found.</p>
						<p className="text-xs opacity-50">
							Upload a document to start extracting policies.
						</p>
					</div>
				) : (
					<Table>
						<TableHeader>
							<TableRow className="hover:bg-transparent border-border/50 bg-muted/20">
								<TableHead className="w-[40%] text-xs">File</TableHead>
								<TableHead className="w-[20%] text-xs">Status</TableHead>
								<TableHead className="w-[25%] text-xs">Current Stage</TableHead>
								<TableHead className="w-[15%] text-right text-xs">
									Result
								</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{validJobs.map((job) => (
								<JobRow key={job.job_id} job={job} onJobClick={onJobClick} />
							))}
						</TableBody>
					</Table>
				)}
			</CardContent>
		</Card>
	);
}

function JobRow({
	job,
	onJobClick,
}: {
	job: IngestJob;
	onJobClick?: (job: IngestJob) => void;
}) {
	const config = STATUS_CONFIG[job.status] || STATUS_CONFIG.QUEUED;
	const StatusIcon = config.icon;

	// Heuristics for display
	const filename = job.stats?.filename || "Unknown Document";
	const fileType = filename.split(".").pop()?.toUpperCase() || "PDF";
	const duration = job.stats?.duration_seconds
		? `${job.stats.duration_seconds.toFixed(1)}s`
		: "--";

	// Interactivity check
	const isClickable = job.status === "COMPLETED" && !!onJobClick;

	return (
		<TableRow
			className={cn(
				"border-border/40 transition-colors group",
				isClickable ? "cursor-pointer hover:bg-muted/50" : "hover:bg-muted/30"
			)}
			onClick={() => isClickable && onJobClick(job)}
		>
			{/* FILE INFO */}
			<TableCell className="py-3">
				<div className="flex items-center gap-3">
					<div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-800 border border-border">
						<span className="text-[9px] font-bold text-muted-foreground">
							{fileType}
						</span>
					</div>
					<div className="flex flex-col min-w-0">
						<span className="truncate font-medium text-sm text-foreground">
							{filename}
						</span>
						<span className="text-[10px] text-muted-foreground font-mono truncate max-w-[150px]">
							{job.job_id}
						</span>
					</div>
				</div>
			</TableCell>

			{/* STATUS BADGE */}
			<TableCell className="py-3">
				<Badge
					variant="outline"
					className={cn(
						"font-mono text-[10px] font-medium px-2 py-0.5 h-6 gap-1.5",
						config.color
					)}
				>
					<StatusIcon
						className={cn("h-3 w-3", config.animate && "animate-spin")}
					/>
					{config.label}
				</Badge>
			</TableCell>

			{/* STAGE MESSAGE */}
			<TableCell className="py-3">
				<p
					className="text-xs text-muted-foreground truncate max-w-[200px]"
					title={job.message}
				>
					{job.message || "Waiting to start..."}
				</p>
			</TableCell>

			{/* METRICS */}
			<TableCell className="py-3 text-right">
				<div className="flex items-center justify-end gap-2">
					<span className="font-mono text-xs font-medium text-foreground/80">
						{job.status === "COMPLETED"
							? `${job.stats?.final_obligations_count ?? 0} Rules`
							: job.status === "FAILED"
								? "Error"
								: duration}
					</span>
					{isClickable && (
						<ChevronRight className="h-4 w-4 text-muted-foreground opacity-50 group-hover:opacity-100 group-hover:text-foreground transition-all" />
					)}
				</div>
			</TableCell>
		</TableRow>
	);
}

function QueueSkeleton({ className }: { className?: string }) {
	return (
		<Card className={cn("border-border/50", className)}>
			<CardHeader className="py-4">
				<Skeleton className="h-4 w-48 bg-muted" />
				<Skeleton className="h-3 w-64 bg-muted mt-2" />
			</CardHeader>
			<CardContent className="p-0">
				<div className="divide-y divide-border/30">
					{Array.from({ length: 3 }).map((_, i) => (
						<div key={i} className="flex items-center gap-4 p-4">
							<Skeleton className="h-8 w-8 rounded-lg bg-muted" />
							<div className="space-y-2 flex-1">
								<Skeleton className="h-3 w-32 bg-muted" />
								<Skeleton className="h-2 w-24 bg-muted" />
							</div>
							<Skeleton className="h-6 w-20 rounded-full bg-muted" />
							<Skeleton className="h-3 w-24 bg-muted" />
						</div>
					))}
				</div>
			</CardContent>
		</Card>
	);
}