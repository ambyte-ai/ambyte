"use client";

import { Activity, Lock, Timer } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AuditLog, Decision } from "@/types/audit";

interface AuditTableProps {
    logs: AuditLog[];
    isLoading: boolean;
    onRowClick: (log: AuditLog) => void;
}

// =============================================================================
// Helper Components
// =============================================================================

function FormatTime({ isoString }: { isoString: string }) {
    const date = new Date(isoString);
    const today = new Date();

    const isToday =
        date.getDate() === today.getDate() &&
        date.getMonth() === today.getMonth() &&
        date.getFullYear() === today.getFullYear();

    const timeString = date.toLocaleTimeString("en-US", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short",
    });

    if (isToday) {
        return <span className="text-foreground/90">Today, {timeString}</span>;
    }

    const dateString = date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
    });

    return <span className="text-muted-foreground">{dateString}, {timeString}</span>;
}

function StatusIcon({ isSealed }: { isSealed: boolean }) {
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <div className="flex items-center justify-center cursor-help">
                    {isSealed ? (
                        <Lock className="h-4 w-4 text-emerald-500" />
                    ) : (
                        <Timer className="h-4 w-4 text-amber-500" />
                    )}
                </div>
            </TooltipTrigger>
            <TooltipContent side="right" className="text-xs">
                {isSealed
                    ? "Sealed (Immutable Cryptographic Block)"
                    : "Buffered (Pending Cryptographic Seal)"}
            </TooltipContent>
        </Tooltip>
    );
}

function DecisionBadge({ decision }: { decision: Decision }) {
    if (decision === "ALLOW") {
        return (
            <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white font-semibold border-transparent rounded shadow-sm px-2">
                ALLOW
            </Badge>
        );
    }
    if (decision === "DENY") {
        return (
            <Badge className="bg-rose-500 hover:bg-rose-600 text-white font-semibold border-transparent rounded shadow-sm px-2">
                DENY
            </Badge>
        );
    }
    if (decision === "DRY_RUN_DENY") {
        return (
            <Badge variant="outline" className="border-amber-500/50 border-dashed text-amber-500 bg-amber-500/10 font-semibold rounded px-2">
                DRY RUN DENY
            </Badge>
        );
    }
    return <Badge variant="outline" className="rounded px-2">{decision}</Badge>;
}

// =============================================================================
// Main Table Component
// =============================================================================

export function AuditTable({ logs, isLoading, onRowClick }: AuditTableProps) {
    if (isLoading && logs.length === 0) {
        return <TableSkeleton />;
    }

    return (
        <Card className="flex flex-col border-border/50 bg-card overflow-hidden shadow-sm flex-1 min-h-0">
            <TooltipProvider>
                <div className="overflow-x-auto flex-1">
                    <Table>
                        <TableHeader className="bg-muted/20 sticky top-0 z-10 backdrop-blur-sm">
                            <TableRow className="hover:bg-transparent border-b border-border/50">
                                <TableHead className="w-[40px] text-center px-2"></TableHead>
                                <TableHead className="w-[180px] text-xs uppercase tracking-wider">Time</TableHead>
                                <TableHead className="w-[200px] text-xs uppercase tracking-wider">Actor</TableHead>
                                <TableHead className="w-[140px] text-xs uppercase tracking-wider">Action</TableHead>
                                <TableHead className="w-[220px] text-xs uppercase tracking-wider">Resource</TableHead>
                                <TableHead className="w-[120px] text-xs uppercase tracking-wider">Decision</TableHead>
                                <TableHead className="text-xs uppercase tracking-wider">Reason</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {logs.length === 0 && !isLoading ? (
                                <TableRow>
                                    <TableCell colSpan={7} className="h-48">
                                        <EmptyState />
                                    </TableCell>
                                </TableRow>
                            ) : (
                                logs.map((log) => {
                                    const isSealed = log.block_id !== null;
                                    const reason = log.reason_trace?.decision_reason || "No explicit reason provided.";

                                    return (
                                        <TableRow
                                            key={log.id}
                                            className="group cursor-pointer hover:bg-muted/30 transition-colors border-border/40"
                                            onClick={() => onRowClick(log)}
                                        >
                                            {/* Status */}
                                            <TableCell className="px-2">
                                                <StatusIcon isSealed={isSealed} />
                                            </TableCell>

                                            {/* Time */}
                                            <TableCell className="font-mono text-xs whitespace-nowrap">
                                                <FormatTime isoString={log.timestamp} />
                                            </TableCell>

                                            {/* Actor */}
                                            <TableCell>
                                                <span className="font-mono text-xs text-foreground/90 truncate block max-w-[180px]" title={log.actor_id}>
                                                    {log.actor_id}
                                                </span>
                                            </TableCell>

                                            {/* Action */}
                                            <TableCell>
                                                <code className="text-[10px] font-mono font-bold uppercase bg-muted/50 border border-border/50 px-1.5 py-0.5 rounded text-muted-foreground whitespace-nowrap">
                                                    [ {log.action} ]
                                                </code>
                                            </TableCell>

                                            {/* Resource */}
                                            <TableCell>
                                                <span
                                                    className="text-xs text-muted-foreground truncate block max-w-[200px]"
                                                    title={log.resource_urn}
                                                    // Optional: Use RTL so the end of the URN is visible if truncated
                                                    dir="rtl"
                                                >
                                                    <span dir="ltr">{log.resource_urn}</span>
                                                </span>
                                            </TableCell>

                                            {/* Decision */}
                                            <TableCell>
                                                <DecisionBadge decision={log.decision} />
                                            </TableCell>

                                            {/* Reason */}
                                            <TableCell>
                                                <span className={cn(
                                                    "text-xs truncate block max-w-[300px]",
                                                    log.decision === "DENY" ? "text-rose-400" : "text-muted-foreground"
                                                )} title={reason}>
                                                    {reason}
                                                </span>
                                            </TableCell>
                                        </TableRow>
                                    );
                                })
                            )}
                        </TableBody>
                    </Table>
                </div>
            </TooltipProvider>

            {/* Footer Summary */}
            {logs.length > 0 && (
                <div className="px-6 py-3 border-t border-border/50 bg-muted/10 text-xs text-muted-foreground shrink-0">
                    Showing <span className="font-medium text-foreground">{logs.length}</span> events in the current view.
                </div>
            )}
        </Card>
    );
}

// =============================================================================
// Skeletons & Empty States
// =============================================================================

function TableSkeleton() {
    return (
        <Card className="flex flex-col border-border/50 bg-card overflow-hidden shadow-sm flex-1 min-h-0">
            <div className="border-b border-border/50 p-4 bg-muted/20">
                <div className="flex gap-4">
                    <Skeleton className="h-4 w-[20px]" />
                    <Skeleton className="h-4 w-[120px]" />
                    <Skeleton className="h-4 w-[150px]" />
                    <Skeleton className="h-4 w-[80px]" />
                    <Skeleton className="h-4 w-[180px]" />
                    <Skeleton className="h-4 w-[80px]" />
                    <Skeleton className="h-4 flex-1" />
                </div>
            </div>
            <div className="divide-y divide-border/30">
                {Array.from({ length: 15 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-4 p-4">
                        <Skeleton className="h-4 w-4 rounded-full" />
                        <Skeleton className="h-3 w-[120px]" />
                        <Skeleton className="h-3 w-[150px]" />
                        <Skeleton className="h-5 w-[80px] rounded" />
                        <Skeleton className="h-3 w-[180px]" />
                        <Skeleton className="h-6 w-[60px] rounded" />
                        <Skeleton className="h-3 flex-1" />
                    </div>
                ))}
            </div>
        </Card>
    );
}

function EmptyState() {
    return (
        <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="h-12 w-12 rounded-full bg-muted/50 flex items-center justify-center mb-4">
                <Activity className="h-6 w-6 text-muted-foreground/50" />
            </div>
            <h3 className="text-sm font-medium text-foreground">No events found</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
                There are no audit logs matching your current filters and time range.
                Try adjusting your search criteria.
            </p>
        </div>
    );
}