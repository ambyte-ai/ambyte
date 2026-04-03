"use client";

import {
    AlertTriangle,
    Check,
    Copy,
    ExternalLink,
    GitBranch,
    ShieldAlert,
    Zap,
} from "lucide-react";
import { useState } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AuditLog } from "@/types/audit";

interface TraceTabProps {
    log: AuditLog;
}

// =============================================================================
// Copy-to-Clipboard Helper
// =============================================================================

function CopyButton({ text, label }: { text: string; label?: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(text);
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
                        className="h-6 w-6 shrink-0 opacity-50 hover:opacity-100 transition-opacity"
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
                    {copied ? "Copied!" : label || "Copy to clipboard"}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

// =============================================================================
// Verdict Banner
// =============================================================================

function VerdictBanner({ log }: { log: AuditLog }) {
    const isDenied = log.decision.includes("DENY");
    const isDryRun = log.decision === "DRY_RUN_DENY";
    const reason =
        log.reason_trace?.decision_reason || "No explicit reason provided.";

    return (
        <div
            className={cn(
                "rounded-xl border p-5 relative overflow-hidden",
                isDenied
                    ? isDryRun
                        ? "border-amber-500/30 bg-amber-500/5"
                        : "border-rose-500/30 bg-rose-500/5"
                    : "border-emerald-500/30 bg-emerald-500/5"
            )}
        >
            {/* Subtle gradient accent */}
            <div
                className={cn(
                    "absolute inset-0 opacity-[0.03]",
                    isDenied
                        ? isDryRun
                            ? "bg-gradient-to-br from-amber-500 to-transparent"
                            : "bg-gradient-to-br from-rose-500 to-transparent"
                        : "bg-gradient-to-br from-emerald-500 to-transparent"
                )}
            />

            <div className="relative z-10">
                {/* Decision Header */}
                <div className="flex items-center gap-3 mb-3">
                    <div
                        className={cn(
                            "h-10 w-10 rounded-lg flex items-center justify-center shrink-0",
                            isDenied
                                ? isDryRun
                                    ? "bg-amber-500/15"
                                    : "bg-rose-500/15"
                                : "bg-emerald-500/15"
                        )}
                    >
                        <ShieldAlert
                            className={cn(
                                "h-5 w-5",
                                isDenied
                                    ? isDryRun
                                        ? "text-amber-500"
                                        : "text-rose-500"
                                    : "text-emerald-500"
                            )}
                        />
                    </div>
                    <div>
                        <h3
                            className={cn(
                                "text-lg font-bold tracking-tight",
                                isDenied
                                    ? isDryRun
                                        ? "text-amber-400"
                                        : "text-rose-400"
                                    : "text-emerald-400"
                            )}
                        >
                            {log.decision === "ALLOW"
                                ? "ACCESS ALLOWED"
                                : log.decision === "DRY_RUN_DENY"
                                  ? "DRY RUN — WOULD DENY"
                                  : "ACCESS DENIED"}
                        </h3>
                        <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                            Action:{" "}
                            <span className="text-foreground/80">
                                {log.action}
                            </span>{" "}
                            on{" "}
                            <span className="text-foreground/80">
                                {log.resource_urn.split(":").slice(-2).join(":")}
                            </span>
                        </p>
                    </div>
                </div>

                {/* Reason */}
                <p className="text-sm text-foreground/80 leading-relaxed pl-[52px]">
                    {reason}
                </p>
            </div>
        </div>
    );
}

// =============================================================================
// Contributing Policies
// =============================================================================

function ContributingPolicies({ log }: { log: AuditLog }) {
    const policies = log.reason_trace?.contributing_policies || [];

    if (policies.length === 0) {
        return (
            <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Contributing Policies
                </h4>
                <p className="text-xs text-muted-foreground italic">
                    No specific policy contributions recorded for this
                    evaluation.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Contributing Policies
                <Badge
                    variant="secondary"
                    className="ml-2 bg-muted/50 text-[10px] px-1.5 py-0"
                >
                    {policies.length}
                </Badge>
            </h4>

            <div className="grid gap-2">
                {policies.map((policy, idx) => (
                    <div
                        key={`${policy.obligation_id}-${idx}`}
                        className="group flex items-start gap-3 p-3 rounded-lg border border-border/50 bg-card/50 hover:border-border hover:bg-card transition-all"
                    >
                        {/* Effect indicator */}
                        <div
                            className={cn(
                                "h-2 w-2 rounded-full mt-1.5 shrink-0",
                                policy.effect === "deny"
                                    ? "bg-rose-500"
                                    : policy.effect === "allow"
                                      ? "bg-emerald-500"
                                      : "bg-amber-500"
                            )}
                        />

                        <div className="flex-1 min-w-0 space-y-1">
                            <div className="flex items-center gap-2">
                                <Link
                                    href={`/obligations/${policy.obligation_id}`}
                                    className="text-sm font-medium text-foreground hover:text-primary transition-colors inline-flex items-center gap-1"
                                >
                                    {policy.obligation_id}
                                    <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-70 transition-opacity" />
                                </Link>
                                <CopyButton
                                    text={policy.obligation_id}
                                    label="Copy Obligation ID"
                                />
                            </div>

                            {policy.source_id && (
                                <p className="text-[10px] font-mono text-muted-foreground">
                                    Source: {policy.source_id}
                                </p>
                            )}

                            <p className="text-xs text-muted-foreground leading-relaxed">
                                {policy.reason}
                            </p>
                        </div>

                        {/* Effect Badge */}
                        <Badge
                            variant="outline"
                            className={cn(
                                "shrink-0 text-[10px] uppercase font-semibold tracking-wider",
                                policy.effect === "deny"
                                    ? "border-rose-500/30 text-rose-400"
                                    : policy.effect === "allow"
                                      ? "border-emerald-500/30 text-emerald-400"
                                      : "border-border text-muted-foreground"
                            )}
                        >
                            {policy.effect}
                        </Badge>
                    </div>
                ))}
            </div>
        </div>
    );
}

// =============================================================================
// Lineage Constraints (Poison Pills)
// =============================================================================

function LineageConstraints({ log }: { log: AuditLog }) {
    const constraints = log.reason_trace?.lineage_constraints || [];

    if (constraints.length === 0) return null;

    return (
        <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                <GitBranch className="h-3.5 w-3.5" />
                Upstream Lineage Constraints
            </h4>

            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-2">
                <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-200/80 leading-relaxed">
                        This resource inherits restrictions from upstream data
                        sources via lineage propagation. The following
                        constraints &quot;poison&quot; downstream usage:
                    </p>
                </div>
                <ul className="pl-6 space-y-1">
                    {constraints.map((constraint, idx) => (
                        <li
                            key={idx}
                            className="text-xs font-mono text-amber-300/90 list-disc"
                        >
                            {constraint}
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}

// =============================================================================
// Cache Status
// =============================================================================

function CacheBadge({ log }: { log: AuditLog }) {
    const cacheHit = log.reason_trace?.cache_hit ?? false;

    return (
        <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
                Engine Response:
            </span>
            <Badge
                variant="outline"
                className={cn(
                    "text-[10px] font-semibold",
                    cacheHit
                        ? "border-indigo-500/30 text-indigo-400 bg-indigo-500/5"
                        : "border-border text-muted-foreground"
                )}
            >
                {cacheHit ? (
                    <>
                        <Zap className="h-3 w-3 mr-1" />
                        Cache Hit — Instant
                    </>
                ) : (
                    "🧠 Engine Computed"
                )}
            </Badge>

            {log.reason_trace?.resolved_policy_hash && (
                <span className="text-[10px] font-mono text-muted-foreground/50 truncate max-w-[120px]" title={log.reason_trace.resolved_policy_hash}>
                    hash: {log.reason_trace.resolved_policy_hash.slice(0, 12)}…
                </span>
            )}
        </div>
    );
}

// =============================================================================
// Main Export
// =============================================================================

export function TraceTab({ log }: TraceTabProps) {
    return (
        <div className="space-y-6">
            {/* 1. The Verdict Banner */}
            <VerdictBanner log={log} />

            {/* 2. Contributing Policies */}
            <ContributingPolicies log={log} />

            {/* 3. Lineage Constraints (conditional) */}
            <LineageConstraints log={log} />

            <Separator className="opacity-30" />

            {/* 4. Cache Status */}
            <CacheBadge log={log} />
        </div>
    );
}
