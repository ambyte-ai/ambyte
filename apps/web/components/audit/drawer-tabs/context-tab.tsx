"use client";

import {
    Bot,
    Check,
    Copy,
    ExternalLink,
    Shield,
    User,
} from "lucide-react";
import { useState } from "react";

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
import { ActorType } from "@/types/audit";

interface ContextTabProps {
    log: AuditLog;
}

// =============================================================================
// Copy Button (shared inline helper)
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
                    {copied ? "Copied!" : label || "Copy"}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

// =============================================================================
// Actor Info Card
// =============================================================================

function ActorCard({ log }: { log: AuditLog }) {
    // The list-view AuditLog only has actor_id (string).
    // We display what we have, and indicate the actor type is unknown at this level.
    const actorId = log.actor_id;

    return (
        <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Actor Details
            </h4>

            <div className="rounded-xl border border-border/50 bg-card/50 overflow-hidden">
                {/* Actor Header */}
                <div className="flex items-center gap-3 p-4 border-b border-border/30 bg-muted/10">
                    <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                        {actorId.includes("@") ? (
                            <User className="h-5 w-5 text-primary" />
                        ) : (
                            <Bot className="h-5 w-5 text-primary" />
                        )}
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                            <span className="font-mono text-sm font-semibold text-foreground truncate">
                                {actorId}
                            </span>
                            <CopyButton text={actorId} label="Copy Actor ID" />
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                            <Badge
                                variant="outline"
                                className="text-[10px] border-border/50 text-muted-foreground"
                            >
                                {actorId.includes("@")
                                    ? "Human"
                                    : "Service Account"}
                            </Badge>
                        </div>
                    </div>
                </div>

                {/* Metadata Rows */}
                <div className="divide-y divide-border/30">
                    <div className="flex items-center justify-between px-4 py-2.5">
                        <span className="text-xs text-muted-foreground">
                            Action Performed
                        </span>
                        <code className="text-[11px] font-mono font-bold uppercase bg-muted/50 border border-border/50 px-1.5 py-0.5 rounded text-muted-foreground">
                            {log.action}
                        </code>
                    </div>
                    <div className="flex items-center justify-between px-4 py-2.5">
                        <span className="text-xs text-muted-foreground">
                            Target Resource
                        </span>
                        <div className="flex items-center gap-1">
                            <code
                                className="text-[11px] font-mono text-foreground/80 truncate max-w-[220px]"
                                title={log.resource_urn}
                            >
                                {log.resource_urn}
                            </code>
                            <CopyButton
                                text={log.resource_urn}
                                label="Copy Resource URN"
                            />
                        </div>
                    </div>
                    <div className="flex items-center justify-between px-4 py-2.5">
                        <span className="text-xs text-muted-foreground">
                            Timestamp
                        </span>
                        <span className="text-xs font-mono text-foreground/80">
                            {new Date(log.timestamp).toLocaleString("en-US", {
                                dateStyle: "medium",
                                timeStyle: "long",
                            })}
                        </span>
                    </div>
                    <div className="flex items-center justify-between px-4 py-2.5">
                        <span className="text-xs text-muted-foreground">
                            Event ID
                        </span>
                        <div className="flex items-center gap-1">
                            <code
                                className="text-[10px] font-mono text-muted-foreground truncate max-w-[180px]"
                                title={log.id}
                            >
                                {log.id}
                            </code>
                            <CopyButton
                                text={log.id}
                                label="Copy Event ID"
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

// =============================================================================
// JSON Viewer
// =============================================================================

function JsonViewer({ data, title }: { data: Record<string, any> | null; title: string }) {
    const [copied, setCopied] = useState(false);
    const jsonString = JSON.stringify(data || {}, null, 2);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(jsonString);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const isEmpty = !data || Object.keys(data).length === 0;

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    {title}
                </h4>
                {!isEmpty && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-muted-foreground hover:text-foreground gap-1.5"
                        onClick={handleCopy}
                    >
                        {copied ? (
                            <>
                                <Check className="h-3 w-3 text-emerald-500" />
                                Copied
                            </>
                        ) : (
                            <>
                                <Copy className="h-3 w-3" />
                                Copy JSON
                            </>
                        )}
                    </Button>
                )}
            </div>

            {isEmpty ? (
                <div className="p-6 text-center rounded-lg border border-dashed bg-muted/5">
                    <p className="text-xs text-muted-foreground italic">
                        No runtime context was attached to this access request.
                    </p>
                </div>
            ) : (
                <div className="relative rounded-xl border border-zinc-800 bg-[#0D0D0D] overflow-hidden shadow-lg">
                    {/* Terminal-style header */}
                    <div className="flex items-center px-4 py-2 border-b border-zinc-800 bg-zinc-900/80">
                        <div className="flex gap-1.5 mr-3">
                            <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
                            <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
                            <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
                        </div>
                        <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
                            request_context
                        </span>
                    </div>

                    {/* JSON Content */}
                    <pre className="p-4 text-emerald-400 font-mono text-xs leading-relaxed overflow-x-auto max-h-[320px] scrollbar-thin">
                        {jsonString}
                    </pre>
                </div>
            )}
        </div>
    );
}

// =============================================================================
// Main Export
// =============================================================================

export function ContextTab({ log }: ContextTabProps) {
    return (
        <div className="space-y-6">
            {/* 1. Actor Details */}
            <ActorCard log={log} />

            <Separator className="opacity-30" />

            {/* 2. Runtime Context JSON */}
            <JsonViewer
                data={log.request_context}
                title="Runtime Context (Engine Input)"
            />
        </div>
    );
}
