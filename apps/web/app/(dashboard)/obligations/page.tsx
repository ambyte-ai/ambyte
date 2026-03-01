"use client";

import { Filter, Search, Shield, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ObligationsTable } from "@/components/obligations/obligations-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useObligations } from "@/hooks/use-obligations";
import { EnforcementLevel } from "@/types/obligation";

export default function ObligationsPage() {
    // State for filters
    const [searchQuery, setSearchQuery] = useState("");
    const [enforcementFilter, setEnforcementFilter] = useState<string>("all");

    // Fetch data hook
    const { obligations, isLoading, refresh, isValidating } = useObligations({
        query: searchQuery,
        enforcement_level:
            enforcementFilter !== "all"
                ? (parseInt(enforcementFilter) as EnforcementLevel)
                : undefined,
    });

    //	const handleSync = async () => {
    // In a real scenario, this might trigger a git pull or re-index via API
    //		await refresh();
    //	}; TODO: Implement sync

    return (
        <div className="flex h-full flex-col gap-6 animate-in fade-in duration-500">
            {/* 
        A. HEADER REGION 
        Control bar with context and primary actions.
      */}
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                    <div className="flex items-center gap-2">
                        <Shield className="h-6 w-6 text-primary" />
                        <h1 className="text-2xl font-bold tracking-tight">Obligations</h1>
                    </div>
                    <p className="text-sm text-muted-foreground">
                        Active policy definitions and enforcement rules.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {/*<Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        //onClick={handleSync}
                        disabled={isValidating}
                    >
                        <RefreshCw
                            className={`h-4 w-4 ${isValidating ? "animate-spin" : ""}`}
                        />
                        Sync
                    </Button>*/}
                    <Button asChild size="sm" className="gap-2">
                        <Link href="/ingest">
                            <UploadCloud className="h-4 w-4" />
                            Ingest Policy
                        </Link>
                    </Button>
                </div>
            </div>

            {/* 
        B. FILTER & SEARCH TOOLBAR 
      */}
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search policies by title, slug, or source..."
                        className="pl-9 bg-card"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
                <div className="flex items-center gap-2">
                    <Select
                        value={enforcementFilter}
                        onValueChange={setEnforcementFilter}
                    >
                        <SelectTrigger className="w-[160px] bg-card">
                            <Filter className="mr-2 h-3.5 w-3.5 opacity-70" />
                            <SelectValue placeholder="Enforcement" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All Levels</SelectItem>
                            <SelectItem value={EnforcementLevel.BLOCKING.toString()}>
                                Blocking
                            </SelectItem>
                            <SelectItem value={EnforcementLevel.AUDIT_ONLY.toString()}>
                                Audit Only
                            </SelectItem>
                            <SelectItem value={EnforcementLevel.NOTIFY_HUMAN.toString()}>
                                Notify Human
                            </SelectItem>
                        </SelectContent>
                    </Select>

                    {/* 
            Placeholder filters for Type and Source.
            Ideally, these would be populated dynamically or mapped to API params if supported.
          */}
                    <Select disabled>
                        <SelectTrigger className="w-[140px] bg-card">
                            <SelectValue placeholder="Type" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All Types</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>

            {/* 
        C. THE DATA TABLE (Master View)
      */}
            <Card className="flex-1 border-border/50 bg-card">
                <ObligationsTable obligations={obligations} isLoading={isLoading} />
            </Card>
        </div>
    );
}
