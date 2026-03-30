"use client";

import {
    Activity,
    AlertTriangle,
    ArrowUpRight,
    BrainCircuit,
    Calendar,
    CheckCircle2,
    Clock,
    Database,
    GitBranch,
    Info,
    Network,
    Server,
    ShieldAlert,
    ShieldCheck,
    User,
    XCircle,
} from "lucide-react";

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
import { useLineageAnalysis, type GraphNode } from "@/hooks/use-lineage";
import { cn } from "@/lib/utils";
import { useLineageStore } from "@/hooks/use-lineage-store";

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

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export function LineageInspector() {
    // 1. Graph State
    const { nodes, edges, selectedNodeId, setSelectedNodeId, setHighlightedPath, highlightedPath } = useLineageStore();

    // Determine if the selected ID is a Node or an Edge
    // React Flow IDs are unique across both arrays.
    const activeNode = nodes.find((n) => n.id === selectedNodeId);
    const activeEdge = edges.find((e) => e.id === selectedNodeId);

    // 2. Diagnostic Data Fetching
    // We only fetch analysis if a NODE is selected (Edges don't have inherited constraints)
    const { analysis, isLoading: isAnalyzing } = useLineageAnalysis(activeNode ? selectedNodeId : null);

    // 3. Handlers
    const handleClose = (open: boolean) => {
        if (!open) setSelectedNodeId(null);
    };

    const handleTraceBlocker = () => {
        if (analysis?.upstream_path) {
            // Append the target node itself so it stays illuminated
            setHighlightedPath([...analysis.upstream_path, analysis.target_urn]);
        }
    };

    // -------------------------------------------------------------------------
    // Render: EMPTY STATE (Hidden)
    // -------------------------------------------------------------------------
    if (!selectedNodeId) {
        return <Sheet open={false} onOpenChange={handleClose}><SheetContent className="w-[500px]" /></Sheet>;
    }

    // -------------------------------------------------------------------------
    // Render: EDGE (Execution Run) VIEW
    // -------------------------------------------------------------------------
    if (activeEdge) {
        const data = activeEdge.data as { run_type?: string; success?: boolean; run_id?: string; actor_id?: string; start_time?: string } | undefined;
        const isSuccess = data?.success;

        return (
            <Sheet open={true} onOpenChange={handleClose}>
                <SheetContent className="w-[400px] sm:w-[500px] p-0 flex flex-col bg-background border-l-border/50">
                    <div className="p-6 pb-4 bg-muted/10 border-b border-border/50">
                        <SheetHeader>
                            <div className="flex items-center gap-2 mb-2">
                                <Badge variant="outline" className="text-[10px] font-mono tracking-wider bg-background">
                                    Execution Run
                                </Badge>
                                {isSuccess ? (
                                    <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 text-[10px]">
                                        <CheckCircle2 className="w-3 h-3 mr-1" /> Success
                                    </Badge>
                                ) : (
                                    <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/20 text-[10px]">
                                        <XCircle className="w-3 h-3 mr-1" /> Failed
                                    </Badge>
                                )}
                            </div>
                            <SheetTitle className="text-xl font-bold flex items-center gap-2">
                                <Activity className="w-5 h-5 text-muted-foreground" />
                                {data?.run_type?.replace(/_/g, " ") || "Data Movement"}
                            </SheetTitle>
                            <SheetDescription className="font-mono text-xs mt-1">
                                ID: {data?.run_id}
                            </SheetDescription>
                        </SheetHeader>
                    </div>

                    <div className="p-6 space-y-6">
                        <div className="space-y-4">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Execution Details</h3>

                            <div className="grid gap-4 rounded-lg border bg-card p-4 shadow-sm">
                                <div className="flex items-center gap-3">
                                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
                                        <User className="h-4 w-4 text-muted-foreground" />
                                    </div>
                                    <div className="flex flex-col">
                                        <span className="text-[10px] text-muted-foreground uppercase font-semibold">Triggered By</span>
                                        <span className="text-sm font-medium">{data?.actor_id || "System"}</span>
                                    </div>
                                </div>

                                <Separator />

                                <div className="grid grid-cols-2 gap-4">
                                    <div className="flex flex-col gap-1">
                                        <span className="text-[10px] text-muted-foreground uppercase font-semibold flex items-center gap-1">
                                            <Calendar className="w-3 h-3" /> Date
                                        </span>
                                        <span className="text-sm">
                                            {data?.start_time ? new Date(data.start_time).toLocaleDateString() : "Unknown"}
                                        </span>
                                    </div>
                                    <div className="flex flex-col gap-1">
                                        <span className="text-[10px] text-muted-foreground uppercase font-semibold flex items-center gap-1">
                                            <Clock className="w-3 h-3" /> Time (UTC)
                                        </span>
                                        <span className="text-sm font-mono">
                                            {data?.start_time ? new Date(data.start_time).toLocaleTimeString() : "--:--:--"}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </SheetContent>
            </Sheet>
        );
    }

    // -------------------------------------------------------------------------
    // Render: NODE (Resource/Model) VIEW
    // -------------------------------------------------------------------------
    if (activeNode) {
        const data = activeNode.data as unknown as GraphNode;
        const isModel = data.node_type === "model";
        const isTraced = highlightedPath.length > 0;

        return (
            <Sheet open={true} onOpenChange={handleClose}>
                <SheetContent className="w-[500px] sm:w-[600px] sm:max-w-none p-0 flex flex-col bg-background border-l-border/50 shadow-2xl">

                    {/* Header */}
                    <div className="p-6 pb-0 bg-muted/10 shrink-0">
                        <SheetHeader className="mb-4">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Badge
                                        variant="secondary"
                                        className={cn(
                                            "uppercase text-[10px] tracking-wide font-semibold",
                                            isModel ? "bg-indigo-500/10 text-indigo-400 border-indigo-500/20" : "bg-primary/10 text-primary border-primary/20"
                                        )}
                                    >
                                        {data.platform}
                                    </Badge>
                                    {isModel && (
                                        <Badge variant="outline" className="text-[10px] font-mono border-indigo-500/30 text-indigo-400">
                                            <BrainCircuit className="w-3 h-3 mr-1" />
                                            AI MODEL
                                        </Badge>
                                    )}
                                </div>

                                {/* Direct Metadata Tags */}
                                <SensitivityBadge level={data.sensitivity} />
                            </div>

                            <SheetTitle className="text-2xl font-bold leading-tight mt-2 flex items-center gap-2">
                                {isModel ? <Network className="w-6 h-6 text-indigo-500" /> : <Database className="w-6 h-6 text-primary" />}
                                {data.label}
                            </SheetTitle>
                            <SheetDescription className="mt-1">
                                <code className="text-[11px] font-mono bg-muted/50 px-1.5 py-0.5 rounded text-muted-foreground truncate block">
                                    {activeNode.id}
                                </code>
                            </SheetDescription>
                        </SheetHeader>

                        {/* Tabs Navigation */}
                        <Tabs defaultValue="governance" className="w-full">
                            <TabsList className="w-full justify-start rounded-none border-b bg-transparent p-0 h-auto">
                                <TabsTrigger
                                    value="governance"
                                    className="relative h-10 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground data-[state=active]:border-primary data-[state=active]:text-foreground"
                                >
                                    <ShieldCheck className="mr-2 h-4 w-4" />
                                    Compliance Posture
                                </TabsTrigger>
                                <TabsTrigger
                                    value="overview"
                                    className="relative h-10 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground data-[state=active]:border-primary data-[state=active]:text-foreground"
                                >
                                    <Info className="mr-2 h-4 w-4" />
                                    Asset Details
                                </TabsTrigger>
                            </TabsList>

                            <ScrollArea className="h-[calc(100vh-140px)]">

                                {/* ---------------------------------------------------- */}
                                {/* TAB 1: GOVERNANCE & POISON PILLS                     */}
                                {/* ---------------------------------------------------- */}
                                <TabsContent value="governance" className="m-0 p-6 space-y-8 outline-none">

                                    {/* Inherited Risk Scores */}
                                    <div className="space-y-3">
                                        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Calculated Inheritance</h3>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="p-4 rounded-xl border bg-card shadow-sm flex flex-col gap-2">
                                                <span className="text-[10px] uppercase text-muted-foreground font-semibold flex items-center gap-1">
                                                    <GitBranch className="w-3 h-3" /> Max Inherited Risk
                                                </span>
                                                {isAnalyzing ? (
                                                    <div className="h-6 w-20 bg-muted animate-pulse rounded" />
                                                ) : (
                                                    <RiskBadge level={analysis?.inherited_risk} />
                                                )}
                                            </div>
                                            <div className="p-4 rounded-xl border bg-card shadow-sm flex flex-col gap-2">
                                                <span className="text-[10px] uppercase text-muted-foreground font-semibold flex items-center gap-1">
                                                    <GitBranch className="w-3 h-3" /> Max Inherited Sensitivity
                                                </span>
                                                {isAnalyzing ? (
                                                    <div className="h-6 w-24 bg-muted animate-pulse rounded" />
                                                ) : (
                                                    <SensitivityBadge level={analysis?.inherited_sensitivity} />
                                                )}
                                            </div>
                                        </div>
                                        <p className="text-[11px] text-muted-foreground leading-relaxed mt-2">
                                            Risk and sensitivity escalate upwards. If this asset consumes from a Highly Restricted source, it inherits that restriction automatically.
                                        </p>
                                    </div>

                                    <Separator />

                                    {/* Poison Pills (Lineage Diagnostics) */}
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between">
                                            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                                                <ShieldAlert className="w-4 h-4" />
                                                Blocking Constraints (Poison Pills)
                                            </h3>
                                        </div>

                                        {isAnalyzing ? (
                                            <div className="h-24 w-full border border-dashed rounded-xl bg-muted/10 animate-pulse flex items-center justify-center text-xs text-muted-foreground">
                                                Analyzing recursive dependencies...
                                            </div>
                                        ) : analysis && analysis.poisoned_constraints.length > 0 ? (
                                            <div className="space-y-4">
                                                {/* The Warning Box */}
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
                                                                <li key={c} className="text-xs font-mono text-rose-400 bg-rose-950/30 px-2 py-1 rounded border border-rose-500/20 truncate">
                                                                    {c}
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    </div>
                                                </div>

                                                {/* THE MAGIC BUTTON */}
                                                <Button
                                                    className="w-full bg-rose-600 hover:bg-rose-700 text-white shadow-lg shadow-rose-900/20"
                                                    onClick={handleTraceBlocker}
                                                    disabled={isTraced}
                                                >
                                                    {isTraced ? "Trace Currently Active on Canvas" : "Visually Trace Blocker in Graph"}
                                                    {!isTraced && <ArrowUpRight className="w-4 h-4 ml-2" />}
                                                </Button>
                                            </div>
                                        ) : (
                                            <div className="p-6 text-center rounded-xl border border-dashed bg-emerald-500/5">
                                                <CheckCircle2 className="h-8 w-8 text-emerald-500/50 mx-auto mb-2" />
                                                <h4 className="text-sm font-medium text-emerald-500">No Upstream Blockers</h4>
                                                <p className="text-xs text-muted-foreground mt-1 max-w-[250px] mx-auto">
                                                    This asset has not inherited any restrictive usage policies from its data sources.
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                </TabsContent>

                                {/* ---------------------------------------------------- */}
                                {/* TAB 2: OVERVIEW & NATIVE TAGS                        */}
                                {/* ---------------------------------------------------- */}
                                <TabsContent value="overview" className="m-0 p-6 space-y-6 outline-none">
                                    <div className="space-y-3">
                                        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Resource Tags</h3>
                                        {data.tags && Object.keys(data.tags).length > 0 ? (
                                            <div className="flex flex-wrap gap-2">
                                                {Object.entries(data.tags).map(([key, val]) => (
                                                    <Badge key={key} variant="secondary" className="bg-muted/50 border-border px-2 py-1 text-xs">
                                                        <span className="opacity-50 mr-1">{key}:</span>{val as string}
                                                    </Badge>
                                                ))}
                                            </div>
                                        ) : (
                                            <p className="text-xs text-muted-foreground italic">No native tags detected.</p>
                                        )}
                                    </div>
                                    <Separator />
                                    <div className="space-y-3">
                                        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Raw Data payload</h3>
                                        <pre className="text-[10px] font-mono bg-muted/30 p-4 rounded-xl border overflow-x-auto text-muted-foreground">
                                            {JSON.stringify(data, null, 2)}
                                        </pre>
                                    </div>
                                </TabsContent>

                            </ScrollArea>
                        </Tabs>
                    </div>
                </SheetContent>
            </Sheet>
        );
    }

    return null;
}