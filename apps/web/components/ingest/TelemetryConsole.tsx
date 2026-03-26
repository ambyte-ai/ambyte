"use client";

import { Terminal } from "lucide-react";
import type { IngestJob } from "@/hooks/use-ingest-jobs";
import { cn } from "@/lib/utils";

interface TelemetryConsoleProps {
	job?: IngestJob;
	className?: string;
}

export function TelemetryConsole({ job, className }: TelemetryConsoleProps) {
	if (!job) {
		return (
			<TerminalWindow className={className}>
				<LogLine type="sys" text="Waiting for job initialization..." />
				<ActiveLine text="Connecting to worker node" />
			</TerminalWindow>
		);
	}

	const isCompleted = job.status === "COMPLETED";
	const isFailed = job.status === "FAILED";
	const stats = job.stats || {};

	return (
		<TerminalWindow className={className}>
			{/* System Initialization */}
			<LogLine type="sys" text={`Job ID assigned: ${job.job_id}`} />
			{stats.filename && (
				<LogLine type="sys" text={`Target document: ${stats.filename}`} />
			)}

			{/* Dynamic Metrics (Render as they become available) */}
			{stats.chunks_processed !== undefined && (
				<LogLine
					type="metric"
					text={`Semantic chunking complete. Generated ${stats.chunks_processed} blocks.`}
				/>
			)}

			{stats.definitions_found !== undefined && (
				<LogLine
					type="metric"
					text={`Glossary extraction complete. Found ${stats.definitions_found} defined terms.`}
				/>
			)}

			{stats.raw_constraints_found !== undefined && (
				<LogLine
					type="metric"
					text={`Rule extraction complete. Identified ${stats.raw_constraints_found} raw constraints.`}
				/>
			)}

			{stats.final_obligations_count !== undefined && (
				<LogLine
					type="success"
					text={`Deduplication complete. Finalized ${stats.final_obligations_count} enforceable obligations.`}
				/>
			)}

			{stats.synced_to_cloud && (
				<LogLine
					type="success"
					text="Successfully synced obligations to Ambyte Control Plane."
				/>
			)}

			{stats.sync_error && (
				<LogLine
					type="error"
					text={`Control Plane Sync Error: ${stats.sync_error}`}
				/>
			)}

			{/* Current Live Status */}
			{!isCompleted && !isFailed && (
				<ActiveLine
					text={`[${job.status}] ${job.message || "Processing..."}`}
				/>
			)}

			{isCompleted && (
				<LogLine
					type="success"
					text={`Pipeline finished successfully in ${stats.duration_seconds || "0.0"}s.`}
				/>
			)}

			{isFailed && (
				<LogLine
					type="error"
					text={`PIPELINE FAILED: ${job.message || "Unknown error."}`}
				/>
			)}
		</TerminalWindow>
	);
}

// -----------------------------------------------------------------------------
// Internal Sub-components
// -----------------------------------------------------------------------------

function TerminalWindow({
	children,
	className,
}: {
	children: React.ReactNode;
	className?: string;
}) {
	return (
		<div
			className={cn(
				"flex flex-col h-full overflow-hidden rounded-xl border border-zinc-800 bg-[#0D0D0D] shadow-2xl",
				className,
			)}
		>
			{/* Fake Window Header */}
			<div className="flex items-center px-4 py-2 border-b border-zinc-800 bg-zinc-900/80">
				<div className="flex gap-1.5 mr-4">
					<div className="h-2.5 w-2.5 rounded-full bg-rose-500/50" />
					<div className="h-2.5 w-2.5 rounded-full bg-amber-500/50" />
					<div className="h-2.5 w-2.5 rounded-full bg-emerald-500/50" />
				</div>
				<div className="flex items-center gap-2 text-xs font-mono text-zinc-500 justify-center flex-1">
					<Terminal className="h-3 w-3" />
					<span>ambyte-ingest-worker --tail</span>
				</div>
			</div>

			{/* Log Area */}
			<div className="flex-1 overflow-y-auto p-4 space-y-1.5 font-mono text-[11px] leading-relaxed">
				{children}
			</div>
		</div>
	);
}

function LogLine({
	type,
	text,
}: {
	type: "sys" | "metric" | "success" | "error";
	text: string;
}) {
	// Timestamp for the log (simulated as current time since we don't store historical timestamps per line) TODO
	const time = new Date().toLocaleTimeString([], {
		hour12: false,
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
	});

	const typeColors = {
		sys: "text-zinc-500",
		metric: "text-indigo-400",
		success: "text-emerald-400",
		error: "text-rose-400",
	};

	const prefixMap = {
		sys: "[SYS]",
		metric: "[METRIC]",
		success: "[SUCCESS]",
		error: "[FATAL]",
	};

	return (
		<div className="flex gap-3 animate-in fade-in slide-in-from-bottom-1 duration-300">
			<span className="text-zinc-600 shrink-0">{time}</span>
			<span className={cn("font-semibold shrink-0", typeColors[type])}>
				{prefixMap[type]}
			</span>
			<span className="text-zinc-300 break-words">{text}</span>
		</div>
	);
}

function ActiveLine({ text }: { text: string }) {
	return (
		<div className="flex gap-3 text-cyan-400 mt-2">
			<span className="shrink-0 animate-pulse">{">"}</span>
			<span className="break-words">
				{text}
				<span className="inline-block w-1.5 h-3 ml-1 bg-cyan-400 animate-pulse align-middle" />
			</span>
		</div>
	);
}
