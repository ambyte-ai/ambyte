"use client";

import { Database, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { InventoryKpis } from "@/components/inventory/inventory-kpis";
import { InventoryTable } from "@/components/inventory/inventory-table";
import { InventoryToolbar } from "@/components/inventory/inventory-toolbar";
import { ResourceDrawer } from "@/components/inventory/resource-drawer";
import { Button } from "@/components/ui/button";
import { type Resource, useInventory } from "@/hooks/use-inventory";
import { cn } from "@/lib/utils";

export default function InventoryPage() {
    // ============================================================================
    // State Management
    // ============================================================================

    // Table & Pagination State
    const [page, setPage] = useState(1);
    const [searchQuery, setSearchQuery] = useState("");
    const [platformFilter, setPlatformFilter] = useState("all");
    const [sensitivityFilter, setSensitivityFilter] = useState("all");

    // Drawer State
    const [selectedResource, setSelectedResource] = useState<Resource | null>(null);

    // ============================================================================
    // Data Fetching
    // ============================================================================

    const { resources, pagination, isLoading, isValidating, refresh } = useInventory({
        page,
        size: 50,
        query: searchQuery,
        platform: platformFilter,
        sensitivity: sensitivityFilter,
    });

    const hasActiveFilters =
        searchQuery !== "" || platformFilter !== "all" || sensitivityFilter !== "all";

    // Reset to page 1 whenever a filter changes
    useEffect(() => {
        setPage(1);
    }, [searchQuery, platformFilter, sensitivityFilter]);

    // ============================================================================
    // Keyboard Shortcuts
    // ============================================================================

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Press '/' to focus the search bar
            if (
                e.key === "/" &&
                document.activeElement?.tagName !== "INPUT" &&
                document.activeElement?.tagName !== "TEXTAREA"
            ) {
                e.preventDefault();
                const searchInput = document.querySelector(
                    'input[placeholder*="Search inventory"]'
                ) as HTMLInputElement;
                searchInput?.focus();
            }
        };

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, []);

    // ============================================================================
    // Render
    // ============================================================================

    return (
        <div className="flex h-full flex-col gap-6 animate-in fade-in duration-500">
            {/* A. HEADER REGION */}
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                    <div className="flex items-center gap-2">
                        <Database className="h-6 w-6 text-primary" />
                        <h1 className="text-2xl font-bold tracking-tight">
                            Data Map & Inventory
                        </h1>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                        Discover, tag, and monitor your data assets across platforms.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        className="gap-2 shadow-sm"
                        onClick={() => refresh()}
                        disabled={isValidating}
                    >
                        <RefreshCw
                            className={cn("h-4 w-4", isValidating && "animate-spin text-primary")}
                        />
                        Sync Connectors
                    </Button>
                </div>
            </div>

            {/* B. KPIs (The "Pulse") */}
            <InventoryKpis
                totalResources={pagination.total}
                currentResources={resources}
                isLoading={isLoading && !isValidating} // Only show skeleton on initial load, not revalidations
            />

            {/* C. TOOLBAR (Search & Filters) */}
            <InventoryToolbar
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                platformFilter={platformFilter}
                onPlatformChange={setPlatformFilter}
                sensitivityFilter={sensitivityFilter}
                onSensitivityChange={setSensitivityFilter}
            />

            {/* D. THE RESOURCE LEDGER (Data Table) */}
            <div className="flex-1">
                <InventoryTable
                    resources={resources}
                    isLoading={isLoading && !isValidating}
                    pagination={pagination}
                    onPageChange={setPage}
                    onRowClick={setSelectedResource}
                    hasActiveFilters={hasActiveFilters}
                />
            </div>

            {/* E. THE DEEP-DIVE DRAWER */}
            <ResourceDrawer
                resource={selectedResource}
                open={!!selectedResource}
                onOpenChange={(open) => !open && setSelectedResource(null)}
            />
        </div>
    );
}