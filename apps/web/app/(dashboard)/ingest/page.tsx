"use client";

import { Activity, ArrowLeft, BrainCircuit, UploadCloud } from "lucide-react";
import { useEffect, useState } from "react";
import { IngestionQueue } from "@/components/dashboard/ingestion-queue";
import { ExtractionResults } from "@/components/ingest/ExtractionResults";
import { FileDropzone } from "@/components/ingest/FileDropzone";
import { HistoricalJobDrawer } from "@/components/ingest/HistoricalJobDrawer";
import { PipelineStepper } from "@/components/ingest/PipelineStepper";
import { TelemetryConsole } from "@/components/ingest/TelemetryConsole";
import { Button } from "@/components/ui/button";
import type { IngestJob } from "@/hooks/use-ingest-jobs";
import { useIngestMutation } from "@/hooks/use-ingest-mutation";
import { useJobPolling } from "@/hooks/use-job-polling";
import type { Obligation } from "@/types/obligation";

type ViewState = "HUB" | "PROCESSING" | "RESULTS";

export default function IngestPage() {
	// ---------------------------------------------------------------------------
	// State Machine
	// ---------------------------------------------------------------------------
	const [viewState, setViewState] = useState<ViewState>("HUB");

	// Active job being processed in the "Theater" view
	const [activeJobId, setActiveJobId] = useState<string | null>(null);

	// Historical job opened from the "Ledger" view (Drawer)
	const [selectedHistoricalJob, setSelectedHistoricalJob] =
		useState<IngestJob | null>(null);

	// ---------------------------------------------------------------------------
	// Hooks
	// ---------------------------------------------------------------------------
	const { uploadFile, isUploading } = useIngestMutation();
	const { job: activeJob, isComplete, isFailed } = useJobPolling(activeJobId);

	// ---------------------------------------------------------------------------
	// Effects & Handlers
	// ---------------------------------------------------------------------------

	// Auto-transition to RESULTS when processing finishes
	useEffect(() => {
		if (viewState === "PROCESSING" && isComplete && activeJob) {
			// Add a tiny delay so the user can see the final "Success" log in the terminal
			// before the UI swaps completely to the results.
			const timer = setTimeout(() => setViewState("RESULTS"), 1000);
			return () => clearTimeout(timer);
		}
	}, [viewState, isComplete, activeJob]);

	const handleUpload = async (file: File) => {
		try {
			const initialJob = await uploadFile(file);
			setActiveJobId(initialJob.job_id);
			setViewState("PROCESSING");
		} catch (error) {
			// Error is caught and logged by the hook, but we catch here
			// to prevent breaking the UI state if it throws.
			console.error("Upload initiation failed", error);
		}
	};

	const handleReset = () => {
		setViewState("HUB");
		setActiveJobId(null);
	};

	const handleHistoricalJobClick = (job: IngestJob) => {
		setSelectedHistoricalJob(job);
	};

	// ---------------------------------------------------------------------------
	// Render: HUB STATE (Default)
	// ---------------------------------------------------------------------------
	if (viewState === "HUB") {
		return (
			<div className="flex flex-col gap-8 animate-in fade-in duration-500 h-full">
				<div>
					<div className="flex items-center gap-2">
						<UploadCloud className="h-6 w-6 text-indigo-500" />
						<h1 className="text-2xl font-bold tracking-tight text-foreground">
							Policy Ingestion
						</h1>
					</div>
					<p className="text-sm text-muted-foreground mt-1">
						Transform raw legal documents into machine-enforceable governance
						policies.
					</p>
				</div>

				<div className="grid grid-cols-1 gap-8 max-w-5xl">
					{/* The Dropzone */}
					<FileDropzone onUpload={handleUpload} isUploading={isUploading} />

					{/* The Ledger (History Table) */}
					<div className="space-y-4">
						<h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
							Ingestion History
						</h3>
						<IngestionQueue onJobClick={handleHistoricalJobClick} />
					</div>
				</div>

				{/* Historical Drawer */}
				<HistoricalJobDrawer
					job={selectedHistoricalJob}
					open={!!selectedHistoricalJob}
					onOpenChange={(open) => !open && setSelectedHistoricalJob(null)}
				/>
			</div>
		);
	}

	// ---------------------------------------------------------------------------
	// Render: PROCESSING STATE (The Theater)
	// ---------------------------------------------------------------------------
	if (viewState === "PROCESSING") {
		return (
			<div className="flex flex-col gap-6 animate-in slide-in-from-bottom-4 duration-500 h-[calc(100vh-8rem)]">
				{/* Header */}
				<div className="flex items-center justify-between shrink-0">
					<div>
						<div className="flex items-center gap-2">
							<Activity className="h-6 w-6 text-indigo-500 animate-pulse" />
							<h1 className="text-2xl font-bold tracking-tight text-foreground">
								Pipeline Active
							</h1>
						</div>
						<p className="text-sm text-muted-foreground mt-1 font-mono">
							Processing: {activeJob?.stats?.filename || "Document"} • Job ID:{" "}
							{activeJobId}
						</p>
					</div>

					<Button
						variant="outline"
						size="sm"
						onClick={handleReset}
						className="border-border text-muted-foreground hover:text-foreground"
					>
						<ArrowLeft className="mr-2 h-4 w-4" />
						Back to Hub
					</Button>
				</div>

				{/* The processing grid */}
				<div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
					{/* Left Column: The Stepper */}
					<div className="lg:col-span-1 rounded-xl border border-border/50 bg-card/50 p-6 overflow-y-auto">
						<h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-8 flex items-center gap-2">
							<BrainCircuit className="h-4 w-4" />
							AI Reasoning Engine
						</h3>
						<PipelineStepper status={activeJob?.status} />
					</div>

					{/* Right Column: The Terminal */}
					<div className="lg:col-span-2 rounded-xl overflow-hidden h-full shadow-2xl ring-1 ring-white/5">
						<TelemetryConsole job={activeJob} className="h-full border-0" />
					</div>
				</div>
			</div>
		);
	}

	// ---------------------------------------------------------------------------
	// Render: RESULTS STATE (The Payoff)
	// ---------------------------------------------------------------------------
	if (viewState === "RESULTS") {
		const extractedObligations: Obligation[] = Array.isArray(
			activeJob?.stats?.obligations,
		)
			? activeJob.stats.obligations
			: [];

		return (
			<ExtractionResults
				obligations={extractedObligations}
				onReset={handleReset}
			/>
		);
	}

	return null; // Fallback (should never be reached)
}
