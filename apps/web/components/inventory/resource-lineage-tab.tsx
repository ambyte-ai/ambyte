"use client";

import { useRouter } from "next/navigation";
import {
    AlertTriangle,
    CheckCircle2,
    Database,
    GitBranch,
    ShieldAlert,
    ShieldCheck,
    Server,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useLineageAnalysis } from "@/hooks/use-lineage";
import { useLineageStore } from "@/hooks/use-lineage-store";
import type { Resource } from "@/hooks/use-inventory";
import { cn } from "@/lib/utils";

interface ResourceLineageTabProps {
    resource: Resource;
}

// -----------------------------------------------------------------------------
// UI Helpers
// -----------------------------------------------------------------------------

function RiskBadge({ level }: { level?: string }) {
    const risk = level?.toUpperCase() || "UNSPECIFIED";
    if (risk === "UNACCEPTABLE" || risk === "HIGH") {
        return (
            <Badge className="bg-rose-500/10 text-rose-500 border-rose-500/20 font-mono text-[10px]">
                <ShieldAlert className="w-3 h-3 mr-1" />
                {risk}
            </Badge>
        );
    }
    if (risk === "MEDIUM") {
        return (
            <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/20 font-mono text-[10px]">
                <AlertTriangle className="w-3 h-3 mr-1" />
                {risk}
            </Badge>
        );
    }
    return (
        <Badge className="bg-muted text-muted-foreground border-border font-mono text-[10px]">
            <ShieldCheck className="w-3 h-3 mr-1" />
            {risk}
        </Badge>
    );
}

function SensitivityBadge({ level }: { level?: string }) {
    const sens = level?.toUpperCase() || "UNSPECIFIED";
    if (sens === "RESTRICTED")
        return <Badge className="bg-rose-500/10 text-rose-500 border-rose-500/20 text-[10px]">{sens}</Badge>;
    if (sens === "CONFIDENTIAL")
        return <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/20 text-[10px]">{sens}</Badge>;
    if (sens === "INTERNAL")
        return <Badge className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-[10px]">{sens}</Badge>;
    if (sens === "PUBLIC")
        return <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 text-[10px]">{sens}</Badge>;
    return <Badge variant="outline" className="text-[10px]">{sens}</Badge>;
}

function parseUrn(urn: string) {
    const parts = urn.split(":");
    const platform = parts[1] || "unknown";
    const name = parts[parts.length - 1] || urn;
    return { platform, name };
}

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export function ResourceLineageTab({ resource }: ResourceLineageTabProps) {
    const router = useRouter();

    // Fetch recursive CTE data for this specific URN
    const { analysis, isLoading, isError } = useLineageAnalysis(resource.urn);

    // Global store actions for deep linking
    const { setSelectedNodeId, setHighlightedPath } = useLineageStore();

    const handleViewInGraph = () => {
        // Pre-populate the Lineage Canvas state
        setSelectedNodeId(resource.urn);
        if (analysis?.upstream_path) {
            // Add the target node itself so it lights up as the destination
            setHighlightedPath([...analysis.upstream_path, resource.urn]);
        }

        // Navigate to the Threat Map
        router.push("/lineage");
    };

    // --- LOADING STATE ---
    if (isLoading) {
        return (
            <div className="space-y-8 animate-in fade-in duration-500">
                <div className="space-y-3">
                    <Skeleton className="h-4 w-40 bg-muted" />
                    <div className="grid grid-cols-2 gap-4">
                        <Skeleton className="h-20 w-full rounded-xl bg-muted/50" />
                        <Skeleton className="h-20 w-full rounded-xl bg-muted/50" />
                    </div>
                </div>
                <Skeleton className="h-32 w-full rounded-xl bg-muted/50" />
                <Skeleton className="h-48 w-full rounded-xl bg-muted/50" />
            </div>
        );
    }

    // --- ERROR STATE ---
    if (isError || !analysis) {
        return (
            <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
                <div className="h-16 w-16 rounded-full bg-rose-500/10 flex items-center justify-center">
                    <ShieldAlert className="h-8 w-8 text-rose-500" />
                </div>
                <div>
                    <h3 className="text-lg font-semibold tracking-tight text-rose-500">
                        Analysis Failed
                    </h3>
                    <p className="text-sm text-muted-foreground max-w-sm mx-auto mt-2">
                        Could not calculate the lineage graph for this resource. Make sure your CLI
                        connectors have recently pushed lineage events.
                    </p>
                </div>
            </div>
        );
    }

    const hasUpstream = analysis.upstream_path.length > 0;
    const hasPoisonPills = analysis.poisoned_constraints.length > 0;

    // --- SUCCESS RENDER ---
    return (
        <div className="space-y-8 animate-in fade-in duration-500 pb-8">
            {/* SECTION A: Inherited Posture */}
            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                        Calculated Inheritance
                    </h3>
                    <Button
                        size="sm"
                        variant="secondary"
                        className="h-8 text-xs bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 hover:text-indigo-300 border border-indigo-500/20"
                        onClick={handleViewInGraph}
                    >
                        <GitBranch className="w-3.5 h-3.5 mr-2" />
                        View in Threat Map
                    </Button>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div className="p-4 rounded-xl border bg-card shadow-sm flex flex-col gap-2">
                        <span className="text-[10px] uppercase text-muted-foreground font-semibold flex items-center gap-1">
                            <GitBranch className="w-3 h-3" /> Max Inherited Risk
                        </span>
                        <RiskBadge level={analysis.inherited_risk} />
                    </div>
                    <div className="p-4 rounded-xl border bg-card shadow-sm flex flex-col gap-2">
                        <span className="text-[10px] uppercase text-muted-foreground font-semibold flex items-center gap-1">
                            <GitBranch className="w-3 h-3" /> Max Inherited Sensitivity
                        </span>
                        <SensitivityBadge level={analysis.inherited_sensitivity} />
                    </div>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed mt-2">
                    Risk and sensitivity escalate upwards. If this asset consumes from a Highly Restricted source, it inherits that restriction automatically.
                </p>
            </div>

            <Separator />

            {/* SECTION B: Poison Pills (Blockers) */}
            <div className="space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4" />
                    Blocking Constraints (Poison Pills)
                </h3>

                {hasPoisonPills ? (
                    <div className="p-4 rounded-xl border border-rose-500/30 bg-rose-500/5 shadow-sm space-y-3">
                        <div className="flex items-start gap-3">
                            <div className="mt-0.5 bg-rose-500/20 p-1.5 rounded-md">
                                <ShieldAlert className="w-4 h-4 text-rose-500" />
                            </div>
                            <div>
                                <h4 className="text-sm font-semibold text-rose-500">Usage Restricted by Ancestor</h4>
                                <p className="text-xs text-rose-500/80 leading-relaxed mt-1">
                                    This asset contains data derived from sources that explicitly forbid secondary usage (e.g., AI Training or Marketing).
                                </p>
                            </div>
                        </div>

                        <div className="pt-3 border-t border-rose-500/20">
                            <span className="text-[10px] font-semibold uppercase text-rose-500/70 block mb-2">Tainted Sources:</span>
                            <ul className="space-y-1.5">
                                {analysis.poisoned_constraints.map(c => (
                                    <li key={c} className="text-xs font-mono text-rose-400 bg-rose-950/30 px-2 py-1 rounded border border-rose-500/20 truncate" title={c}>
                                        {c}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                ) : (
                    <div className="p-5 text-center rounded-xl border border-dashed bg-emerald-500/5">
                        <CheckCircle2 className="h-8 w-8 text-emerald-500/50 mx-auto mb-2" />
                        <h4 className="text-sm font-medium text-emerald-500">No Upstream Blockers</h4>
                        <p className="text-xs text-muted-foreground mt-1 max-w-[250px] mx-auto">
                            This asset has not inherited any restrictive usage policies from its data sources.
                        </p>
                    </div>
                )}
            </div>

            <Separator />

            {/* SECTION C: Upstream Dependency Path */}
            <div className="space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                    <Database className="w-4 h-4" />
                    Upstream Dependency Path
                </h3>

                {!hasUpstream ? (
                    <div className="p-5 text-center rounded-xl border border-dashed bg-muted/5">
                        <Server className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                        <h4 className="text-sm font-medium text-foreground">Root Origin Asset</h4>
                        <p className="text-xs text-muted-foreground mt-1 max-w-[250px] mx-auto">
                            This resource has no upstream dependencies. It is the origin point of the data.
                        </p>
                    </div>
                ) : (
                    <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
                        <div className="p-3 border-b bg-muted/20">
                            <span className="text-xs font-medium text-muted-foreground">
                                {analysis.upstream_path.length} Ancestor Nodes
                            </span>
                        </div>
                        <ScrollArea className="max-h-[250px]">
                            <div className="divide-y divide-border/50">
                                {analysis.upstream_path.map((urn, idx) => {
                                    const { platform, name } = parseUrn(urn);
                                    const isPoisoned = analysis.poisoned_constraints.includes(urn);

                                    return (
                                        <div key={idx} className="p-3 flex items-center gap-3 hover:bg-muted/30 transition-colors">
                                            <div className={cn(
                                                "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
                                                isPoisoned ? "bg-rose-500/10 border-rose-500/30 text-rose-500" : "bg-muted/50 border-border/50 text-muted-foreground"
                                            )}>
                                                {platform.includes("snowflake") || platform.includes("postgres")
                                                    ? <Database className="h-4 w-4" />
                                                    : <Server className="h-4 w-4" />}
                                            </div>
                                            <div className="flex flex-col min-w-0 flex-1">
                                                <div className="flex items-center gap-2">
                                                    <span className={cn(
                                                        "font-medium text-sm truncate",
                                                        isPoisoned ? "text-rose-500" : "text-foreground"
                                                    )}>
                                                        {name}
                                                    </span>
                                                    {isPoisoned && (
                                                        <ShieldAlert className="h-3 w-3 text-rose-500 shrink-0" />
                                                    )}
                                                </div>
                                                <span className="text-[10px] text-muted-foreground font-mono truncate">
                                                    {platform.toUpperCase()}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </ScrollArea>
                    </div>
                )}
            </div>
        </div>
    );
}