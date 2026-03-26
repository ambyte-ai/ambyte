"use client";

import { ExtractionResults } from "@/components/ingest/ExtractionResults";
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import type { IngestJob } from "@/hooks/use-ingest-jobs";
import type { Obligation } from "@/types/obligation";

interface HistoricalJobDrawerProps {
	job: IngestJob | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function HistoricalJobDrawer({
	job,
	open,
	onOpenChange,
}: HistoricalJobDrawerProps) {
	// If no job is selected, we still render the Sheet (controlled by 'open')
	// but with no content to prevent layout jumps during closing animations.
	if (!job) {
		return (
			<Sheet open={open} onOpenChange={onOpenChange}>
				<SheetContent className="sm:max-w-[90vw] w-[1200px] p-0" />
			</Sheet>
		);
	}

	// Safely extract the obligations array from the job stats.
	// The backend serializes these as JSON dicts, which perfectly map to our frontend TS interface.
	const obligations: Obligation[] = Array.isArray(job.stats?.obligations)
		? job.stats.obligations
		: [];

	const filename = job.stats?.filename || "Unknown Document";
	const duration = job.stats?.duration_seconds
		? `${job.stats.duration_seconds.toFixed(1)}s`
		: "Unknown time";

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent
				// We use a very wide drawer (90vw up to 1200px) because the ExtractionResults
				// component uses a complex 2-column layout that needs horizontal space.
				className="sm:max-w-[90vw] w-[1200px] p-0 flex flex-col bg-background border-l-border/50 shadow-2xl"
			>
				{/* Drawer Header: Context about the historical job */}
				<div className="px-6 py-4 border-b border-border/50 bg-muted/10 shrink-0">
					<SheetHeader>
						<SheetTitle className="text-lg font-bold flex items-center gap-2">
							Historical Ingestion:{" "}
							<span className="font-mono text-primary font-normal">
								{filename}
							</span>
						</SheetTitle>
						<SheetDescription className="text-xs">
							Processed in {duration} • Job ID:{" "}
							<span className="font-mono">{job.job_id}</span>
						</SheetDescription>
					</SheetHeader>
				</div>

				{/* 
					Drawer Body: Reusing the exact same component from Phase 2.
					We pass `onOpenChange(false)` to the `onReset` prop so the "Process Another" 
					or "Back" buttons inside ExtractionResults simply close the drawer.
				*/}
				<div className="flex-1 overflow-hidden p-6 pt-2">
					<ExtractionResults
						obligations={obligations}
						onReset={() => onOpenChange(false)}
					/>
				</div>
			</SheetContent>
		</Sheet>
	);
}
