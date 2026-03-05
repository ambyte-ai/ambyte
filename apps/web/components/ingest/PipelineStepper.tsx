"use client";

import {
    BookOpen,
    BrainCircuit,
    CheckCircle2,
    CloudUpload,
    Combine,
    Database,
    FileText,
    Loader2,
    Scissors,
    Timer,
    XCircle,
} from "lucide-react";
import type { IngestStatus } from "@/hooks/use-ingest-jobs";
import { cn } from "@/lib/utils";

// Define the exact order of the pipeline matching the backend enum
const PIPELINE_STEPS = [
    {
        id: "QUEUED",
        title: "Queued",
        description: "Waiting for an available worker.",
        icon: Timer,
    },
    {
        id: "PARSING",
        title: "Parsing Document",
        description: "Extracting text, layout, and tables via OCR.",
        icon: FileText,
    },
    {
        id: "CHUNKING",
        title: "Semantic Chunking",
        description: "Splitting text into logical, context-aware blocks.",
        icon: Scissors,
    },
    {
        id: "EMBEDDING",
        title: "Vector Embedding",
        description: "Generating mathematical representations for the knowledge graph.",
        icon: Database,
    },
    {
        id: "DEFINING",
        title: "Extracting Glossary",
        description: "Identifying capitalized defined terms (e.g., 'Customer Data').",
        icon: BookOpen,
    },
    {
        id: "EXTRACTION",
        title: "Rule Extraction",
        description: "Applying regulatory logic to extract technical constraints.",
        icon: BrainCircuit,
    },
    {
        id: "MERGING",
        title: "Deduplication",
        description: "Consolidating duplicate rules and resolving conflicts.",
        icon: Combine,
    },
    {
        id: "SYNCING",
        title: "Cloud Sync",
        description: "Pushing finalized obligations to the Control Plane.",
        icon: CloudUpload,
    },
];

interface PipelineStepperProps {
    status?: IngestStatus;
    className?: string;
}

export function PipelineStepper({ status = "QUEUED", className }: PipelineStepperProps) {
    const isFailed = status === "FAILED";
    const isCompleted = status === "COMPLETED";

    // Determine the index of the currently active step
    const currentIndex = isCompleted
        ? PIPELINE_STEPS.length // All done
        : isFailed
            ? PIPELINE_STEPS.length // Show failure at the end or pause where it died
            : PIPELINE_STEPS.findIndex((s) => s.id === status);

    return (
        <div className={cn("flex flex-col", className)}>
            {PIPELINE_STEPS.map((step, index) => {
                const isPast = index < currentIndex;
                const isActive = index === currentIndex && !isFailed && !isCompleted;
                const isErrorStep = isFailed && index === currentIndex;

                // Determine colors based on state
                let iconColor = "text-muted-foreground";
                let bgColor = "bg-muted/30 border-border";
                let lineColor = "bg-border";

                if (isPast) {
                    iconColor = "text-emerald-500";
                    bgColor = "bg-emerald-500/10 border-emerald-500/30";
                    lineColor = "bg-emerald-500/50";
                } else if (isActive) {
                    iconColor = "text-indigo-400";
                    bgColor = "bg-indigo-500/10 border-indigo-500/30 shadow-[0_0_15px_-3px_rgba(99,102,241,0.2)]";
                    lineColor = "bg-border";
                } else if (isErrorStep) {
                    iconColor = "text-rose-500";
                    bgColor = "bg-rose-500/10 border-rose-500/30 shadow-[0_0_15px_-3px_rgba(244,63,94,0.2)]";
                    lineColor = "bg-border";
                }

                const Icon = isPast ? CheckCircle2 : isErrorStep ? XCircle : step.icon;

                return (
                    <div key={step.id} className="relative flex items-start gap-4 pb-6 last:pb-0">
                        {/* Connecting Line */}
                        {index !== PIPELINE_STEPS.length - 1 && (
                            <div
                                className={cn(
                                    "absolute left-5 top-10 bottom-0 w-px -translate-x-1/2 transition-colors duration-500",
                                    lineColor
                                )}
                            />
                        )}

                        {/* Icon Circle */}
                        <div
                            className={cn(
                                "relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-all duration-500",
                                bgColor,
                                isActive && "ring-4 ring-indigo-500/10"
                            )}
                        >
                            {isActive ? (
                                <Loader2 className={cn("h-4 w-4 animate-spin", iconColor)} />
                            ) : (
                                <Icon className={cn("h-4 w-4", iconColor)} />
                            )}
                        </div>

                        {/* Text Content */}
                        <div className="flex flex-col pt-2.5">
                            <h4
                                className={cn(
                                    "text-sm font-semibold tracking-tight transition-colors duration-300",
                                    isActive || isPast ? "text-foreground" : "text-muted-foreground",
                                    isErrorStep && "text-rose-500"
                                )}
                            >
                                {step.title}
                            </h4>
                            <p
                                className={cn(
                                    "text-xs mt-1 transition-colors duration-300",
                                    isActive ? "text-muted-foreground" : "text-muted-foreground/50"
                                )}
                            >
                                {step.description}
                            </p>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}