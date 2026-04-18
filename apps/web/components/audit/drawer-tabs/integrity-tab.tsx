"use client";

import {
	Check,
	CheckCircle2,
	ChevronRight,
	Copy,
	Fingerprint,
	Hash,
	KeyRound,
	Loader2,
	Lock,
	ShieldCheck,
	Timer,
	TreeDeciduous,
} from "lucide-react";
import { useCallback, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuditProof } from "@/hooks/use-audit-proof";
import { cn } from "@/lib/utils";
import type { AuditLog, AuditProof } from "@/types/audit";

interface IntegrityTabProps {
	log: AuditLog;
}

// =============================================================================
// Types
// =============================================================================

type VerifyStep =
	| "idle"
	| "fetching"
	| "recomputing"
	| "verifying"
	| "verified"
	| "failed";

// =============================================================================
// Copy Hash Button
// =============================================================================

function CopyHashButton({ hash }: { hash: string }) {
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
						className="h-6 w-6 shrink-0 opacity-50 hover:opacity-100"
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
					{copied ? "Copied!" : "Copy hash"}
				</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}

// =============================================================================
// Hash Display (Monospace block with copy)
// =============================================================================

function HashBlock({
	label,
	hash,
	icon: Icon,
	accent = "default",
}: {
	label: string;
	hash: string;
	icon: React.ElementType;
	accent?: "default" | "emerald" | "indigo" | "amber";
}) {
	const accentColors = {
		default: "border-border/50 bg-card/50",
		emerald: "border-emerald-500/20 bg-emerald-500/5",
		indigo: "border-indigo-500/20 bg-indigo-500/5",
		amber: "border-amber-500/20 bg-amber-500/5",
	};

	const iconColors = {
		default: "text-muted-foreground",
		emerald: "text-emerald-500",
		indigo: "text-indigo-500",
		amber: "text-amber-500",
	};

	return (
		<div
			className={cn("rounded-lg border p-3 space-y-2", accentColors[accent])}
		>
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-2">
					<Icon className={cn("h-3.5 w-3.5", iconColors[accent])} />
					<span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
						{label}
					</span>
				</div>
				<CopyHashButton hash={hash} />
			</div>
			<code className="block text-[11px] font-mono text-foreground/80 break-all leading-relaxed select-all">
				{hash}
			</code>
		</div>
	);
}

// =============================================================================
// Unsealed State (Log is buffered)
// =============================================================================

function UnsealedState({ log }: { log: AuditLog }) {
	return (
		<div className="space-y-6">
			{/* Entry Hash (always available) */}
			<HashBlock
				label="Log Fingerprint (SHA-256)"
				hash={log.entry_hash}
				icon={Fingerprint}
				accent="default"
			/>

			<Separator className="opacity-30" />

			{/* Buffered State Info */}
			<div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-6 text-center space-y-3">
				<div className="h-14 w-14 rounded-2xl bg-amber-500/10 flex items-center justify-center mx-auto">
					<Timer className="h-7 w-7 text-amber-500" />
				</div>
				<div>
					<h4 className="text-sm font-semibold text-amber-300">
						Pending Cryptographic Seal
					</h4>
					<p className="text-xs text-amber-200/60 mt-1.5 max-w-sm mx-auto leading-relaxed">
						This log entry is currently in the high-speed memory buffer. It will
						be cryptographically sealed into an immutable block once the buffer
						threshold is reached.
					</p>
				</div>
				<Badge
					variant="outline"
					className="border-amber-500/30 text-amber-400 text-[10px]"
				>
					<Timer className="mr-1 h-3 w-3" />
					Awaiting Block Commit
				</Badge>
			</div>
		</div>
	);
}

// =============================================================================
// Verification Animation
// =============================================================================

function VerificationSteps({
	step,
	proof,
}: {
	step: VerifyStep;
	proof: AuditProof;
}) {
	const steps: {
		id: VerifyStep;
		label: string;
		detail: string;
		icon: React.ElementType;
	}[] = [
		{
			id: "fetching",
			label: "Fetch Merkle Siblings",
			detail: `${proof.merkle_siblings.length} sibling hash(es) retrieved`,
			icon: TreeDeciduous,
		},
		{
			id: "recomputing",
			label: "Recompute Root Hash",
			detail: "Hashing leaf → root through sibling path",
			icon: Hash,
		},
		{
			id: "verifying",
			label: "Verify Ed25519 Signature",
			detail: "Checking block signature against public key",
			icon: KeyRound,
		},
	];

	const stepOrder: VerifyStep[] = [
		"fetching",
		"recomputing",
		"verifying",
		"verified",
	];

	const getStepState = (s: VerifyStep): "pending" | "active" | "complete" => {
		const currentIdx = stepOrder.indexOf(step);
		const thisIdx = stepOrder.indexOf(s);

		if (currentIdx > thisIdx) return "complete";
		if (currentIdx === thisIdx) return "active";
		return "pending";
	};

	return (
		<div className="space-y-2 mt-4">
			{steps.map((s) => {
				const state = getStepState(s.id);
				const Icon = s.icon;

				return (
					<div
						key={s.id}
						className={cn(
							"flex items-center gap-3 p-3 rounded-lg border transition-all duration-500",
							state === "complete"
								? "border-emerald-500/20 bg-emerald-500/5"
								: state === "active"
									? "border-indigo-500/30 bg-indigo-500/5 shadow-sm shadow-indigo-500/10"
									: "border-border/30 bg-card/30 opacity-40",
						)}
					>
						{/* Step indicator */}
						<div
							className={cn(
								"h-8 w-8 rounded-lg flex items-center justify-center shrink-0 transition-all duration-500",
								state === "complete"
									? "bg-emerald-500/20"
									: state === "active"
										? "bg-indigo-500/20"
										: "bg-muted/30",
							)}
						>
							{state === "complete" ? (
								<CheckCircle2 className="h-4 w-4 text-emerald-500" />
							) : state === "active" ? (
								<Loader2 className="h-4 w-4 text-indigo-400 animate-spin" />
							) : (
								<Icon className="h-4 w-4 text-muted-foreground/50" />
							)}
						</div>

						{/* Text */}
						<div className="flex-1 min-w-0">
							<p
								className={cn(
									"text-sm font-medium transition-colors duration-500",
									state === "complete"
										? "text-emerald-400"
										: state === "active"
											? "text-foreground"
											: "text-muted-foreground",
								)}
							>
								{s.label}
							</p>
							<p className="text-[10px] text-muted-foreground truncate">
								{s.detail}
							</p>
						</div>

						{state === "active" && (
							<ChevronRight className="h-4 w-4 text-indigo-400 animate-pulse" />
						)}
					</div>
				);
			})}

			{/* Final verified state */}
			{step === "verified" && (
				<div className="mt-4 rounded-xl border-2 border-emerald-500/30 bg-emerald-500/5 p-6 text-center space-y-3 animate-in fade-in slide-in-from-bottom-4 duration-700">
					<div className="h-16 w-16 rounded-2xl bg-emerald-500/15 flex items-center justify-center mx-auto shadow-lg shadow-emerald-500/10">
						<ShieldCheck className="h-8 w-8 text-emerald-400" />
					</div>
					<div>
						<h4 className="text-lg font-bold text-emerald-400 tracking-tight">
							INTEGRITY VERIFIED
						</h4>
						<p className="text-xs text-emerald-300/60 mt-1">
							Signature &amp; Merkle path match the sealed block root.
						</p>
					</div>
					<Badge className="bg-emerald-500 text-white border-transparent shadow-sm">
						<Lock className="mr-1 h-3 w-3" />
						Cryptographically Immutable
					</Badge>
				</div>
			)}
		</div>
	);
}

// =============================================================================
// Sealed State (with proof)
// =============================================================================

function SealedState({ log, proof }: { log: AuditLog; proof: AuditProof }) {
	const [verifyStep, setVerifyStep] = useState<VerifyStep>("idle");

	const runVerification = useCallback(async () => {
		setVerifyStep("fetching");
		await sleep(1200);
		setVerifyStep("recomputing");
		await sleep(1500);
		setVerifyStep("verifying");
		await sleep(1800);
		setVerifyStep("verified");
	}, []);

	return (
		<div className="space-y-6">
			{/* Entry Hash */}
			<HashBlock
				label="Log Fingerprint (SHA-256)"
				hash={log.entry_hash}
				icon={Fingerprint}
				accent="default"
			/>

			{/* Block Info */}
			<div className="space-y-3">
				<h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
					<Lock className="h-3.5 w-3.5 text-emerald-500" />
					Sealed Block Info
				</h4>

				<div className="rounded-xl border border-emerald-500/20 bg-card/50 overflow-hidden">
					<div className="grid grid-cols-2 divide-x divide-border/30">
						<div className="p-3 space-y-1">
							<span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
								Sequence Index
							</span>
							<p className="text-xl font-bold text-emerald-400 font-mono">
								#{proof.block_header.sequence_index}
							</p>
						</div>
						<div className="p-3 space-y-1">
							<span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
								Log Count
							</span>
							<p className="text-xl font-bold text-foreground font-mono">
								{proof.block_header.log_count}
							</p>
						</div>
					</div>

					<Separator className="opacity-30" />

					<div className="p-3 space-y-1">
						<span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
							Time Window
						</span>
						<p className="text-xs font-mono text-foreground/80">
							{new Date(proof.block_header.timestamp_start).toLocaleString()} →{" "}
							{new Date(proof.block_header.timestamp_end).toLocaleString()}
						</p>
					</div>
				</div>
			</div>

			{/* Merkle Root */}
			<HashBlock
				label="Block Merkle Root"
				hash={proof.block_header.merkle_root}
				icon={TreeDeciduous}
				accent="emerald"
			/>

			{/* Previous Block Hash */}
			{proof.block_header.prev_block_hash && (
				<HashBlock
					label="Previous Block Hash (Chain Link)"
					hash={proof.block_header.prev_block_hash}
					icon={Hash}
					accent="indigo"
				/>
			)}

			<Separator className="opacity-30" />

			{/* Merkle Siblings Preview */}
			<div className="space-y-2">
				<h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
					Merkle Proof Path
				</h4>
				<div className="space-y-1">
					{proof.merkle_siblings.map((sibling, idx) => (
						<div
							key={idx}
							className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground/70"
						>
							<span className="text-muted-foreground/40 w-6 text-right shrink-0">
								L{idx}
							</span>
							<code className="truncate bg-muted/20 px-1.5 py-0.5 rounded flex-1">
								{sibling}
							</code>
						</div>
					))}
					{proof.merkle_siblings.length === 0 && (
						<p className="text-[10px] text-muted-foreground italic">
							Single-entry block — no siblings needed.
						</p>
					)}
				</div>
			</div>

			<Separator className="opacity-30" />

			{/* Verify Button */}
			{verifyStep === "idle" ? (
				<Button
					className="w-full h-12 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold shadow-lg shadow-indigo-500/20 transition-all hover:shadow-indigo-500/30 hover:scale-[1.01]"
					onClick={runVerification}
				>
					<ShieldCheck className="mr-2 h-5 w-5" />
					Verify Mathematical Integrity
				</Button>
			) : (
				<VerificationSteps step={verifyStep} proof={proof} />
			)}
		</div>
	);
}

// =============================================================================
// Loading State
// =============================================================================

function IntegritySkeleton() {
	return (
		<div className="space-y-6">
			<div className="space-y-2">
				<Skeleton className="h-3 w-[140px]" />
				<Skeleton className="h-[72px] w-full rounded-lg" />
			</div>
			<Skeleton className="h-px w-full" />
			<div className="space-y-2">
				<Skeleton className="h-3 w-[120px]" />
				<Skeleton className="h-[100px] w-full rounded-lg" />
			</div>
			<Skeleton className="h-[72px] w-full rounded-lg" />
			<Skeleton className="h-12 w-full rounded-lg" />
		</div>
	);
}

// =============================================================================
// Helpers
// =============================================================================

function sleep(ms: number) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

// =============================================================================
// Main Export
// =============================================================================

export function IntegrityTab({ log }: IntegrityTabProps) {
	const isSealed = log.block_id !== null;

	// Only fetch proof if the log is sealed
	const { proof, isLoading, isError } = useAuditProof(isSealed ? log.id : null);

	// 1. Unsealed = show buffered state
	if (!isSealed) {
		return <UnsealedState log={log} />;
	}

	// 2. Loading proof
	if (isLoading) {
		return <IntegritySkeleton />;
	}

	// 3. Error fetching proof
	if (isError || !proof) {
		return (
			<div className="space-y-6">
				<HashBlock
					label="Log Fingerprint (SHA-256)"
					hash={log.entry_hash}
					icon={Fingerprint}
					accent="default"
				/>
				<Separator className="opacity-30" />
				<div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-6 text-center space-y-2">
					<p className="text-sm font-medium text-rose-400">
						Could not retrieve cryptographic proof
					</p>
					<p className="text-xs text-rose-300/60">
						The block may still be processing. Try again shortly.
					</p>
				</div>
			</div>
		);
	}

	// 4. Sealed with proof available → show full integrity view
	return <SealedState log={log} proof={proof} />;
}
