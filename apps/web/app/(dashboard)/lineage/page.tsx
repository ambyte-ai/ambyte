"use client";

import { ReactFlowProvider } from "@xyflow/react";
import { GitBranch, ShieldAlert } from "lucide-react";

import { LineageCanvas } from "@/components/lineage/lineage-canvas";
import { LineageHud } from "@/components/lineage/lineage-hud";
import { LineageInspector } from "@/components/lineage/lineage-inspector";

/**
 * The Compliance-Aware Graph (Lineage View)
 * 
 * UX Vision: 
 * A "Cybersecurity Threat Map" for data compliance. Instead of just showing 
 * what data moved where, this interface visually proves how legal constraints 
 * ("Poison Pills") infect downstream datasets and AI models.
 */
export default function LineagePage() {
    return (
        <div className="flex flex-col h-[calc(100vh-8rem)] gap-4 animate-in fade-in duration-500">
            {/* 
			  A. HEADER REGION 
			  Sets the context and mood for the diagnostic tool.
			*/}
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between shrink-0">
                <div>
                    <div className="flex items-center gap-2">
                        <GitBranch className="h-6 w-6 text-indigo-500" />
                        <h1 className="text-2xl font-bold tracking-tight text-foreground">
                            Compliance Topology
                        </h1>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                        Interactive threat map for data lineage, risk propagation, and "Poison Pill" diagnostics.
                    </p>
                </div>

                <div className="flex items-center gap-3">
                    {/* "What-If" Analysis Teaser (Future Phase) */}
                    <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted/30 border border-border/50 text-xs text-muted-foreground cursor-not-allowed opacity-70" title="Coming soon: Select two nodes to simulate a join">
                        <ShieldAlert className="w-3.5 h-3.5" />
                        Simulate Join (What-If)
                    </div>
                </div>
            </div>

            {/* 
			  B. THE CANVAS WRAPPER
			  Provides the bounds for the graph. Must be relative so the HUD 
			  can float absolutely over it.
			*/}
            <div className="flex-1 relative rounded-xl border border-zinc-800 bg-[#09090b] shadow-[0_0_40px_-15px_rgba(99,102,241,0.1)] overflow-hidden ring-1 ring-white/5">

                {/* 
				  ReactFlowProvider allows sibling components (HUD, Inspector) 
				  to hook into the canvas state (e.g., `useReactFlow().fitView()`)
				*/}
                <ReactFlowProvider>

                    {/* Floating Toolbar (Lenses & Search) */}
                    <LineageHud />

                    {/* The Interactive DAG */}
                    <LineageCanvas />

                    {/* The Side Drawer (Diagnostic Panel) */}
                    <LineageInspector />

                </ReactFlowProvider>

            </div>
        </div>
    );
}