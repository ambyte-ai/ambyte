import { Handle, Position } from "@xyflow/react";
import { BrainCircuit, Cpu, Network, ShieldAlert } from "lucide-react";
import { useLineageStore } from "@/hooks/use-lineage-store";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/hooks/use-lineage";

// Map model types to icons (from your Lineage Event schema)
const ModelIcon = ({ type, className }: { type: string; className?: string }) => {
    const t = type?.toUpperCase();
    if (t === "LLM") return <BrainCircuit className={cn("text-indigo-400", className)} />;
    if (t === "COMPUTER_VISION") return <Network className={cn("text-violet-400", className)} />;
    return <Cpu className={cn("text-fuchsia-400", className)} />;
};

export function ModelNode({ data, id }: { data: GraphNode; id: string }) {
    const { selectedNodeId, highlightedPath, activeLens } = useLineageStore();

    const isSelected = selectedNodeId === id;
    const isHighlighted = highlightedPath.length === 0 || highlightedPath.includes(id);

    // Lens logic (e.g., dim non-AI nodes in AI Lens)
    let lensOpacityClass = "";
    if (activeLens === "PRIVACY") {
        lensOpacityClass = "opacity-30 grayscale"; // Models don't usually have PII columns
    }

    return (
        <div
            className={cn(
                "relative group w-[280px] rounded-xl transition-all duration-500 cursor-pointer bg-background",
                // Models get a gradient border wrapper to distinguish them from tables
                "p-[2px] bg-gradient-to-br from-indigo-500/50 via-purple-500/20 to-fuchsia-500/50",
                isSelected && "ring-2 ring-primary ring-offset-2 ring-offset-background",
                !isHighlighted && "opacity-20 scale-95 pointer-events-none",
                lensOpacityClass
            )}
        >
            {/* Inner Card to hide the gradient except for the border */}
            <div className="rounded-[10px] bg-card h-full w-full p-4 flex flex-col gap-3 relative overflow-hidden">

                {/* Background Glow Effect */}
                <div className="absolute -top-10 -right-10 w-24 h-24 bg-indigo-500/10 blur-2xl rounded-full" />

                <Handle type="target" position={Position.Left} className="w-3 h-3 bg-indigo-500 border-2 border-background" />

                {/* Header */}
                <div className="flex items-center gap-3 relative z-10">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                        <ModelIcon type={data.platform} className="h-5 w-5" />
                    </div>
                    <div className="flex flex-col min-w-0 flex-1">
                        <span className="font-bold text-sm text-foreground truncate">
                            {data.label}
                        </span>
                        <span className="text-[10px] text-indigo-400 font-mono tracking-wider uppercase">
                            {data.platform === "unknown" ? "AI MODEL" : data.platform}
                        </span>
                    </div>
                </div>

                {/* Footer Badges */}
                <div className="flex items-center justify-between mt-1 relative z-10">
                    <div className="flex gap-2">
                        {/* Risk Level Badge */}
                        <span
                            className={cn(
                                "text-[9px] px-1.5 py-0.5 rounded font-mono font-semibold uppercase border",
                                data.risk_level === "HIGH" || data.risk_level === "UNACCEPTABLE"
                                    ? "bg-rose-500/10 text-rose-500 border-rose-500/20"
                                    : "bg-muted text-muted-foreground border-border"
                            )}
                        >
                            RISK: {data.risk_level}
                        </span>
                    </div>

                    {/* Poison Pill Inherited (The downstream infection) */}
                    {data.is_ai_restricted && (
                        <div
                            className="flex items-center gap-1 text-[10px] font-bold text-rose-500 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20"
                            title="Model was trained on restricted upstream data (Poison Pill)"
                        >
                            <ShieldAlert className="h-3 w-3" />
                            <span>TAINTED</span>
                        </div>
                    )}
                </div>

                <Handle type="source" position={Position.Right} className="w-3 h-3 bg-fuchsia-500 border-2 border-background" />
            </div>
        </div>
    );
}