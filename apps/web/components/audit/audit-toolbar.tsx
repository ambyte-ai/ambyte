"use client";

import { Filter, Search, Terminal, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import type { Decision } from "@/types/audit";
import { cn } from "@/lib/utils";

interface AuditToolbarProps {
    searchQuery: string;
    onSearchChange: (query: string) => void;
    decisionFilter: Decision | "ALL";
    onDecisionChange: (decision: Decision | "ALL") => void;
    isLiveTail: boolean;
    onLiveTailChange: (isLive: boolean) => void;
    // Optional additional filters (e.g., Action Type)
    actionFilter?: string;
    onActionChange?: (action: string) => void;
}

const ACTIONS = [
    { value: "all", label: "All Actions" },
    { value: "read", label: "Read / Select" },
    { value: "write", label: "Write / Insert" },
    { value: "delete", label: "Delete / Drop" },
    { value: "ai_training", label: "AI Training" },
    { value: "ai_fine_tuning", label: "AI Fine-Tuning" },
    { value: "ai_rag_query", label: "RAG Retrieval" },
];

export function AuditToolbar({
    searchQuery,
    onSearchChange,
    decisionFilter,
    onDecisionChange,
    isLiveTail,
    onLiveTailChange,
    actionFilter = "all",
    onActionChange = () => { },
}: AuditToolbarProps) {
    // -------------------------------------------------------------------------
    // State & Debounce
    // -------------------------------------------------------------------------
    const [localQuery, setLocalQuery] = useState(searchQuery);

    // Sync local state if parent resets it
    useEffect(() => {
        setLocalQuery(searchQuery);
    }, [searchQuery]);

    // Debounce typing to avoid spamming the backend or stuttering client filters
    useEffect(() => {
        const timer = setTimeout(() => {
            if (localQuery !== searchQuery) {
                onSearchChange(localQuery);
            }
        }, 300);

        return () => clearTimeout(timer);
    }, [localQuery, searchQuery, onSearchChange]);

    // -------------------------------------------------------------------------
    // Keyboard Shortcuts
    // -------------------------------------------------------------------------
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Press '/' to focus search
            if (
                e.key === "/" &&
                document.activeElement?.tagName !== "INPUT" &&
                document.activeElement?.tagName !== "TEXTAREA"
            ) {
                e.preventDefault();
                const searchInput = document.querySelector(
                    'input[placeholder*="Search logs"]'
                ) as HTMLInputElement;
                searchInput?.focus();
            }
        };

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, []);

    // -------------------------------------------------------------------------
    // Render
    // -------------------------------------------------------------------------

    const hasFilters =
        localQuery !== "" || decisionFilter !== "ALL" || actionFilter !== "all";

    const handleClearFilters = () => {
        setLocalQuery("");
        onSearchChange("");
        onDecisionChange("ALL");
        if (onActionChange) onActionChange("all");
    };

    return (
        <div className="flex flex-col gap-4 md:flex-row md:items-center">

            {/* 1. Omni-Search */}
            <div className="relative flex-1">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                    placeholder="Search logs by Actor ID, URN, or Hash (Press '/')..."
                    className="pl-9 bg-card border-border/50 focus-visible:ring-primary/50 transition-all shadow-sm h-9"
                    value={localQuery}
                    onChange={(e) => setLocalQuery(e.target.value)}
                />
            </div>

            {/* 2. Control Group */}
            <div className="flex flex-wrap items-center gap-3">

                {/* A. Decision Toggle (Segmented Control) */}
                <Tabs
                    value={decisionFilter}
                    onValueChange={(v) => onDecisionChange(v as Decision | "ALL")}
                    className="h-9"
                >
                    <TabsList className="h-9 grid w-[260px] grid-cols-3 bg-muted/50 border border-border/50 p-0.5">
                        <TabsTrigger value="ALL" className="text-xs h-full rounded-md data-[state=active]:bg-background data-[state=active]:shadow-sm">
                            All
                        </TabsTrigger>
                        <TabsTrigger value="ALLOW" className="text-xs h-full rounded-md data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-500 data-[state=active]:shadow-sm">
                            Allowed
                        </TabsTrigger>
                        <TabsTrigger value="DENY" className="text-xs h-full rounded-md data-[state=active]:bg-rose-500/10 data-[state=active]:text-rose-500 data-[state=active]:shadow-sm">
                            Denied
                        </TabsTrigger>
                    </TabsList>
                </Tabs>

                {/* B. Action Filter */}
                <Select value={actionFilter} onValueChange={onActionChange}>
                    <SelectTrigger className="w-[160px] bg-card border-border/50 shadow-sm h-9">
                        <Filter className="mr-2 h-3.5 w-3.5 opacity-70" />
                        <SelectValue placeholder="Action" />
                    </SelectTrigger>
                    <SelectContent>
                        {ACTIONS.map((act) => (
                            <SelectItem key={act.value} value={act.value}>
                                {act.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>

                {/* C. Clear Filters */}
                {hasFilters && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleClearFilters}
                        className="h-9 px-2 text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    >
                        <X className="h-4 w-4 mr-1" />
                        Clear
                    </Button>
                )}

                {/* D. Live Tail Switch */}
                <div className="flex items-center gap-2 pl-2 border-l border-border h-6">
                    <Switch
                        id="live-tail"
                        checked={isLiveTail}
                        onCheckedChange={onLiveTailChange}
                        className={cn(isLiveTail && "data-[state=checked]:bg-indigo-500")}
                    />
                    <Label
                        htmlFor="live-tail"
                        className={cn(
                            "text-xs font-semibold uppercase tracking-wider cursor-pointer select-none flex items-center gap-1.5 transition-colors",
                            isLiveTail ? "text-indigo-400" : "text-muted-foreground"
                        )}
                    >
                        <Terminal className="h-3 w-3" />
                        Live Tail
                        {isLiveTail && (
                            <span className="relative flex h-2 w-2 ml-1">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                            </span>
                        )}
                    </Label>
                </div>

            </div>
        </div>
    );
}