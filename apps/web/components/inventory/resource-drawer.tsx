"use client";

import {
    Check,
    Copy,
    Database,
    GitBranch,
    Server,
    ShieldAlert,
    ShieldCheck,
    TerminalSquare,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ConstraintIcon } from "@/components/obligations/constraint-icon";
import { EnforcementBadge } from "@/components/obligations/enforcement-badge";
import { ResourceLineageTab } from "@/components/inventory/resource-lineage-tab";
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
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Resource } from "@/hooks/use-inventory";
import { useObligations } from "@/hooks/use-obligations";
import type { Obligation } from "@/types/obligation";

interface ResourceDrawerProps {
    resource: Resource | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

// =============================================================================
// Helper: Client-Side Resource Matcher
// Simulates the Python rules-engine logic for UI previews
// =============================================================================

function wildcardToRegExp(pattern: string): RegExp {
    const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`^${escaped.replace(/\*/g, ".*")}$`);
}

function doesPolicyApply(resource: Resource, obligation: Obligation): boolean {
    const target = obligation.target;
    const urn = resource.urn;
    const tags = resource.attributes?.tags || {};

    // 1. Empty selector = False (Safety)
    if (
        (!target.match_tags || Object.keys(target.match_tags).length === 0) &&
        (!target.include_patterns || target.include_patterns.length === 0)
    ) {
        return false;
    }

    // 2. Check Exclusions (Fast Fail)
    if (target.exclude_patterns && target.exclude_patterns.length > 0) {
        for (const pattern of target.exclude_patterns) {
            if (wildcardToRegExp(pattern).test(urn)) return false;
        }
    }

    // 3. Check Tags (AND logic)
    if (target.match_tags && Object.keys(target.match_tags).length > 0) {
        for (const [key, requiredVal] of Object.entries(target.match_tags)) {
            if (String(tags[key]) !== String(requiredVal)) return false;
        }
    }

    // 4. Check Inclusions (OR logic)
    if (!target.include_patterns || target.include_patterns.length === 0) {
        return true; // Passed tag checks, no specific patterns required
    }

    for (const pattern of target.include_patterns) {
        if (wildcardToRegExp(pattern).test(urn)) return true;
    }

    return false;
}

// =============================================================================
// Main Component
// =============================================================================

export function ResourceDrawer({
    resource,
    open,
    onOpenChange,
}: ResourceDrawerProps) {
    const [isCopied, setIsCopied] = useState(false);

    // Fetch all active obligations to calculate "Applied Policies"
    const { obligations } = useObligations();

    const appliedPolicies = useMemo(() => {
        if (!resource || !obligations) return [];
        return obligations.filter((ob) => doesPolicyApply(resource, ob));
    }, [resource, obligations]);

    if (!resource) return null;

    const handleCopyUrn = async () => {
        await navigator.clipboard.writeText(resource.urn);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
    };

    const displayName =
        resource.name || resource.urn.split(":").pop() || "Unknown Resource";
    const hasColumns =
        resource.attributes?.columns && resource.attributes.columns.length > 0;

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent className="w-[500px] sm:w-[600px] sm:max-w-none p-0 flex flex-col bg-background border-l-border/50 shadow-2xl">
                {/* Header Area */}
                <div className="p-6 pb-4 bg-muted/10 shrink-0">
                    <SheetHeader className="mb-4">
                        <div className="flex items-center gap-2 mb-2">
                            <Badge
                                variant="secondary"
                                className="uppercase text-[10px] tracking-wide font-semibold bg-primary/10 text-primary border-primary/20"
                            >
                                {resource.platform}
                            </Badge>
                            {resource.attributes?.table_type && (
                                <Badge variant="outline" className="text-[10px] font-mono">
                                    {resource.attributes.table_type}
                                </Badge>
                            )}
                        </div>
                        <SheetTitle className="text-2xl font-bold leading-tight flex items-center gap-2">
                            {displayName}
                        </SheetTitle>
                        <SheetDescription className="flex items-center gap-2 mt-2">
                            <code className="text-[11px] font-mono bg-muted/50 px-1.5 py-0.5 rounded text-muted-foreground truncate flex-1">
                                {resource.urn}
                            </code>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 shrink-0"
                                onClick={handleCopyUrn}
                                title="Copy URN"
                            >
                                {isCopied ? (
                                    <Check className="h-3 w-3 text-emerald-500" />
                                ) : (
                                    <Copy className="h-3 w-3" />
                                )}
                            </Button>
                        </SheetDescription>
                    </SheetHeader>
                </div>

                <Separator />

                {/* Tabbed Content */}
                <Tabs defaultValue="overview" className="flex-1 flex flex-col min-h-0">
                    <div className="px-6 shrink-0">
                        <TabsList className="w-full justify-start rounded-none border-b bg-transparent p-0 h-auto">
                            <TabsTrigger
                                value="overview"
                                className="relative h-10 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground"
                            >
                                <Database className="mr-2 h-4 w-4" />
                                Overview & Schema
                            </TabsTrigger>
                            <TabsTrigger
                                value="policies"
                                className="relative h-10 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground"
                            >
                                <ShieldCheck className="mr-2 h-4 w-4" />
                                Applied Policies
                                {appliedPolicies.length > 0 && (
                                    <Badge className="ml-2 bg-indigo-500 text-white h-5 px-1.5 min-w-[20px] flex items-center justify-center">
                                        {appliedPolicies.length}
                                    </Badge>
                                )}
                            </TabsTrigger>
                            <TabsTrigger
                                value="lineage"
                                className="relative h-10 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground"
                            >
                                <GitBranch className="mr-2 h-4 w-4" />
                                Lineage
                            </TabsTrigger>
                        </TabsList>
                    </div>

                    <ScrollArea className="flex-1 p-6">
                        {/* =======================================================
                            TAB 1: OVERVIEW & SCHEMA
                        ======================================================= */}
                        <TabsContent
                            value="overview"
                            className="m-0 space-y-6 outline-none"
                        >
                            {/* Metadata Grid */}
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-1 p-3 rounded-lg border bg-card shadow-sm">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                                        Owner
                                    </p>
                                    <p className="text-sm font-medium">
                                        {resource.attributes?.owner || (
                                            <span className="italic text-muted-foreground">
                                                Unassigned
                                            </span>
                                        )}
                                    </p>
                                </div>
                                <div className="space-y-1 p-3 rounded-lg border bg-card shadow-sm">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                                        Location
                                    </p>
                                    <p
                                        className="text-sm font-mono truncate"
                                        title={resource.attributes?.storage_location}
                                    >
                                        {resource.attributes?.storage_location || "N/A"}
                                    </p>
                                </div>
                                <div className="space-y-1 p-3 rounded-lg border bg-card shadow-sm">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                                        Discovered At
                                    </p>
                                    <p className="text-sm">
                                        {new Date(resource.created_at).toLocaleDateString()}
                                    </p>
                                </div>
                                <div className="space-y-1 p-3 rounded-lg border bg-card shadow-sm">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                                        Last Synced
                                    </p>
                                    <p className="text-sm">
                                        {new Date(resource.updated_at).toLocaleString()}
                                    </p>
                                </div>
                            </div>

                            {/* Tags List */}
                            <div className="space-y-3">
                                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
                                    Resource Tags
                                </h3>
                                {resource.attributes?.tags &&
                                    Object.keys(resource.attributes.tags).length > 0 ? (
                                    <div className="flex flex-wrap gap-2">
                                        {Object.entries(resource.attributes.tags).map(
                                            ([key, val]) => (
                                                <Badge
                                                    key={key}
                                                    variant="secondary"
                                                    className="bg-muted/50 border-border px-2 py-1 text-xs"
                                                >
                                                    <span className="opacity-50 mr-1">{key}:</span>
                                                    {val}
                                                </Badge>
                                            ),
                                        )}
                                    </div>
                                ) : (
                                    <p className="text-xs text-muted-foreground italic">
                                        No tags detected. Policies targeting specific tags will not
                                        apply here.
                                    </p>
                                )}
                            </div>

                            <Separator />

                            {/* Schema Table */}
                            <div className="space-y-3">
                                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
                                    Schema & Columns
                                </h3>
                                {hasColumns ? (
                                    <div className="rounded-lg border bg-card overflow-hidden">
                                        <Table>
                                            <TableHeader className="bg-muted/30">
                                                <TableRow className="hover:bg-transparent">
                                                    <TableHead className="h-8 text-xs">Name</TableHead>
                                                    <TableHead className="h-8 text-xs">Type</TableHead>
                                                    <TableHead className="h-8 text-xs">Tags</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {resource.attributes.columns?.map((col, idx) => {
                                                    // Check if column is flagged as sensitive
                                                    const isPii =
                                                        col.tags?.pii === "true" ||
                                                        col.tags?.["governance.pii_category"] ||
                                                        col.tags?.["governance.is_sensitive"] === "true";

                                                    return (
                                                        <TableRow key={idx} className="hover:bg-muted/10">
                                                            <TableCell className="py-2">
                                                                <div className="flex items-center gap-2">
                                                                    <span className="font-medium text-sm">
                                                                        {col.name}
                                                                    </span>
                                                                    {isPii && (
                                                                        <span title="Sensitive / PII">
                                                                            <ShieldAlert className="h-3.5 w-3.5 text-rose-500" />
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            </TableCell>
                                                            <TableCell className="py-2 font-mono text-[10px] text-muted-foreground">
                                                                {col.type}
                                                            </TableCell>
                                                            <TableCell className="py-2">
                                                                <div className="flex flex-wrap gap-1">
                                                                    {Object.entries(col.tags || {}).map(
                                                                        ([k, v]) => (
                                                                            <span
                                                                                key={k}
                                                                                className="text-[9px] font-mono bg-muted px-1 rounded text-muted-foreground"
                                                                            >
                                                                                {k}:{v}
                                                                            </span>
                                                                        ),
                                                                    )}
                                                                </div>
                                                            </TableCell>
                                                        </TableRow>
                                                    );
                                                })}
                                            </TableBody>
                                        </Table>
                                    </div>
                                ) : (
                                    <div className="p-8 text-center rounded-lg border border-dashed bg-muted/5">
                                        <Server className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                                        <p className="text-sm text-muted-foreground">
                                            No schema information available for this resource.
                                        </p>
                                    </div>
                                )}
                            </div>
                        </TabsContent>

                        {/* =======================================================
                            TAB 2: APPLIED POLICIES
                        ======================================================= */}
                        <TabsContent
                            value="policies"
                            className="m-0 space-y-6 outline-none"
                        >
                            <div className="space-y-4">
                                <p className="text-sm text-muted-foreground leading-relaxed">
                                    The reasoning engine matched the following active obligations
                                    to this resource based on its URN and tags.
                                </p>

                                {appliedPolicies.length > 0 ? (
                                    <div className="grid gap-3">
                                        {appliedPolicies.map((ob) => (
                                            <div
                                                key={ob.id}
                                                className="flex flex-col gap-2 p-4 rounded-xl border border-border/50 bg-card shadow-sm hover:border-border transition-colors"
                                            >
                                                <div className="flex items-start justify-between gap-2">
                                                    <div className="flex items-center gap-2 overflow-hidden">
                                                        <ConstraintIcon
                                                            obligation={ob}
                                                            className="shrink-0"
                                                        />
                                                        <span className="font-semibold text-sm truncate text-foreground">
                                                            {ob.title}
                                                        </span>
                                                    </div>
                                                    <EnforcementBadge
                                                        level={ob.enforcement_level}
                                                        showIcon={false}
                                                        className="shrink-0 scale-90 origin-top-right"
                                                    />
                                                </div>
                                                <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
                                                    {ob.description}
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="p-8 text-center rounded-lg border border-dashed bg-muted/5 flex flex-col items-center">
                                        <ShieldCheck className="h-10 w-10 text-emerald-500/30 mb-3" />
                                        <h4 className="text-sm font-medium">No Policies Applied</h4>
                                        <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                                            This resource is not governed by any active Ambyte rules.
                                            Access is allowed by default.
                                        </p>
                                    </div>
                                )}
                            </div>

                            {/* Simulate Access Box */}
                            <div className="mt-8 rounded-xl border border-zinc-800 bg-[#0D0D0D] shadow-xl overflow-hidden">
                                <div className="flex items-center px-4 py-2 border-b border-zinc-800 bg-zinc-900/80">
                                    <TerminalSquare className="h-4 w-4 text-zinc-500 mr-2" />
                                    <span className="text-xs font-mono text-zinc-400">
                                        Test Enforcement via CLI
                                    </span>
                                </div>
                                <div className="p-4 font-mono text-[11px] leading-relaxed">
                                    <div className="text-zinc-500 mb-2">
                                        # Simulate a decision check against this resource
                                    </div>
                                    <div className="flex flex-wrap gap-x-1">
                                        <span className="text-cyan-400">ambyte</span>
                                        <span className="text-zinc-300">check</span>
                                        <span className="text-indigo-300">--resource</span>
                                        <span className="text-emerald-400 break-all">
                                            &quot;{resource.urn}&quot;
                                        </span>
                                        <span className="text-indigo-300">--action</span>
                                        <span className="text-emerald-400">&quot;read&quot;</span>
                                    </div>
                                </div>
                            </div>
                        </TabsContent>

                        {/* =======================================================
                            TAB 3: LINEAGE
                        ======================================================= */}
                        <TabsContent value="lineage" className="m-0 p-6 outline-none">
                            <ResourceLineageTab resource={resource} />
                        </TabsContent>
                    </ScrollArea>
                </Tabs>
            </SheetContent>
        </Sheet>
    );
}
