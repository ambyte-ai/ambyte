"use client";

import {
	Check,
	Copy,
	FileSearch,
	Fingerprint,
	Lock,
	Timer,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AuditLog } from "@/types/audit";
import { ContextTab } from "./drawer-tabs/context-tab";
import { IntegrityTab } from "./drawer-tabs/integrity-tab";
import { TraceTab } from "./drawer-tabs/trace-tab";

// =============================================================================
// Props
// =============================================================================

interface AuditDrawerProps {
	log: AuditLog | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

// =============================================================================
// Helpers
// =============================================================================

function DecisionBadgeLarge({ decision }: { decision: string }) {
	if (decision === "ALLOW") {
		return (
			<Badge className="bg-emerald-500 hover:bg-emerald-600 text-white font-bold border-transparent rounded-md shadow-sm px-3 py-1 text-xs">
				ALLOWED
			</Badge>
		);
	}
	if (decision === "DENY") {
		return (
			<Badge className="bg-rose-500 hover:bg-rose-600 text-white font-bold border-transparent rounded-md shadow-sm px-3 py-1 text-xs">
				DENIED
			</Badge>
		);
	}
	if (decision === "DRY_RUN_DENY") {
		return (
			<Badge
				variant="outline"
				className="border-amber-500/50 border-dashed text-amber-500 bg-amber-500/10 font-bold rounded-md px-3 py-1 text-xs"
			>
				DRY RUN DENY
			</Badge>
		);
	}
	return (
		<Badge variant="outline" className="rounded-md px-3 py-1 text-xs">
			{decision}
		</Badge>
	);
}

function CopyEntryHash({ hash }: { hash: string }) {
	const [copied, setCopied] = useState(false);

	const handleCopy = async () => {
		await navigator.clipboard.writeText(hash);
		setCopied(true);
		setTimeout(() => setCopied(false), 2000);
	};

	return (
		<TooltipProvider>
			<Tooltip>
				<TooltipTrigger asChild>
					<Button
						variant="ghost"
						size="icon"
						className="h-6 w-6 shrink-0"
						onClick={handleCopy}
					>
						{copied ? (
							<Check className="h-3 w-3 text-emerald-500" />
						) : (
							<Copy className="h-3 w-3" />
						)}
					</Button>
				</TooltipTrigger>
				<TooltipContent side="top" className="text-xs">
					{copied ? "Copied!" : "Copy entry hash"}
				</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}

// =============================================================================
// Main Component
// =============================================================================

export function AuditDrawer({ log, open, onOpenChange }: AuditDrawerProps) {
	if (!log) return null;

	const isSealed = log.block_id !== null;
	const timeString = new Date(log.timestamp).toLocaleString("en-US", {
		dateStyle: "medium",
		timeStyle: "short",
	});

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent className="w-[550px] sm:w-[650px] lg:w-[750px] sm:max-w-none p-0 flex flex-col bg-background border-l-border/50 shadow-2xl">
				{/* =========================================================
                    Header
                ========================================================= */}
				<div className="p-6 pb-4 bg-muted/10 shrink-0">
					<SheetHeader className="mb-3">
						{/* Top row: badges */}
						<div className="flex items-center gap-2 mb-2 flex-wrap">
							<DecisionBadgeLarge decision={log.decision} />

							{/* Seal Status */}
							<Badge
								variant="outline"
								className={cn(
									"text-[10px] font-semibold gap-1",
									isSealed
										? "border-emerald-500/30 text-emerald-400"
										: "border-amber-500/30 text-amber-400",
								)}
							>
								{isSealed ? (
									<Lock className="h-3 w-3" />
								) : (
									<Timer className="h-3 w-3" />
								)}
								{isSealed ? "Sealed" : "Buffered"}
							</Badge>

							{/* Action */}
							<code className="text-[10px] font-mono font-bold uppercase bg-muted/50 border border-border/50 px-1.5 py-0.5 rounded text-muted-foreground">
								[ {log.action} ]
							</code>
						</div>

						{/* Title: Actor + Resource */}
						<SheetTitle className="text-xl font-bold leading-tight">
							{log.actor_id}
						</SheetTitle>

						<SheetDescription className="flex items-center gap-2 mt-1.5">
							<code
								className="text-[11px] font-mono bg-muted/50 px-1.5 py-0.5 rounded text-muted-foreground truncate flex-1"
								title={log.resource_urn}
							>
								{log.resource_urn}
							</code>
							<CopyEntryHash hash={log.entry_hash} />
						</SheetDescription>

						{/* Timestamp */}
						<p className="text-[10px] text-muted-foreground/60 mt-1 font-mono">
							{timeString}
						</p>
					</SheetHeader>
				</div>

				<Separator />

				{/* =========================================================
                    Tabbed Content
                ========================================================= */}
				<Tabs defaultValue="trace" className="flex-1 flex flex-col min-h-0">
					<div className="px-6 shrink-0">
						<TabsList className="w-full justify-start rounded-none border-b bg-transparent p-0 h-auto">
							<TabsTrigger
								value="trace"
								className="relative h-10 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground"
							>
								<FileSearch className="mr-2 h-4 w-4" />
								Evaluation Trace
							</TabsTrigger>
							<TabsTrigger
								value="context"
								className="relative h-10 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground"
							>
								<FileSearch className="mr-2 h-4 w-4" />
								Request Context
							</TabsTrigger>
							<TabsTrigger
								value="integrity"
								className="relative h-10 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground"
							>
								<Fingerprint className="mr-2 h-4 w-4" />
								Integrity
								{isSealed && (
									<span className="ml-1.5 h-2 w-2 rounded-full bg-emerald-500 inline-block" />
								)}
							</TabsTrigger>
						</TabsList>
					</div>

					<ScrollArea className="flex-1 p-6">
						{/* Tab 1: Evaluation Trace (The "Why") */}
						<TabsContent value="trace" className="m-0 outline-none">
							<TraceTab log={log} />
						</TabsContent>

						{/* Tab 2: Request Context (The "What") */}
						<TabsContent value="context" className="m-0 outline-none">
							<ContextTab log={log} />
						</TabsContent>

						{/* Tab 3: Cryptographic Integrity (The "Trust") */}
						<TabsContent value="integrity" className="m-0 outline-none">
							<IntegrityTab log={log} />
						</TabsContent>
					</ScrollArea>
				</Tabs>
			</SheetContent>
		</Sheet>
	);
}
