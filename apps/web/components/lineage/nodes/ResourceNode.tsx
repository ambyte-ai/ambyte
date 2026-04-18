import { Handle, Position } from "@xyflow/react";
import { Cloud, Database, FileText, Server, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { GraphNode } from "@/hooks/use-lineage";
import { useLineageStore } from "@/hooks/use-lineage-store";
import { cn } from "@/lib/utils";

// Map platforms to specific icons
const PlatformIcon = ({
	platform,
	className,
}: {
	platform: string;
	className?: string;
}) => {
	const p = platform.toLowerCase();
	if (p.includes("snowflake"))
		return <Database className={cn("text-cyan-500", className)} />;
	if (p.includes("databricks"))
		return <Server className={cn("text-orange-500", className)} />;
	if (p.includes("s3") || p.includes("aws"))
		return <Cloud className={cn("text-yellow-500", className)} />;
	if (p.includes("local") || p.includes("file"))
		return <FileText className={cn("text-zinc-500", className)} />;
	return <Database className={cn("text-muted-foreground", className)} />;
};

export function ResourceNode({ data, id }: { data: GraphNode; id: string }) {
	// 1. Connect to Zustand Store for interactivity
	const { selectedNodeId, highlightedPath, activeLens } = useLineageStore();

	// 2. Compute View States
	const isSelected = selectedNodeId === id;
	const isHighlighted =
		highlightedPath.length === 0 || highlightedPath.includes(id);

	// 3. Compute Lens Effects
	// E.g., if "AI_RISK" lens is active, only highlight restricted nodes
	let lensOpacityClass = "";
	if (activeLens === "AI_RISK" && !data.is_ai_restricted) {
		lensOpacityClass = "opacity-30 grayscale";
	} else if (activeLens === "PRIVACY" && data.sensitivity === "PUBLIC") {
		// Example: In Privacy lens, ignore public data
		lensOpacityClass = "opacity-30 grayscale";
	}

	// 4. Compute Sensitivity Ring (Border Color)
	const sensitivityColors: Record<string, string> = {
		RESTRICTED: "border-rose-500/50 shadow-[0_0_15px_-3px_rgba(244,63,94,0.3)]",
		HIGH: "border-rose-500/50 shadow-[0_0_15px_-3px_rgba(244,63,94,0.3)]",
		CONFIDENTIAL:
			"border-amber-500/50 shadow-[0_0_15px_-3px_rgba(245,158,11,0.2)]",
		INTERNAL: "border-blue-500/30",
		PUBLIC: "border-emerald-500/30",
		UNSPECIFIED: "border-border/50",
	};
	const borderClass =
		sensitivityColors[data.sensitivity?.toUpperCase()] ||
		sensitivityColors.UNSPECIFIED;

	return (
		<div
			className={cn(
				"relative group w-[280px] rounded-xl bg-card transition-all duration-500 cursor-pointer",
				// Base border is defined by sensitivity. If selected, overriding with primary ring
				borderClass,
				"border-2",
				isSelected &&
					"ring-2 ring-primary ring-offset-2 ring-offset-background border-primary",
				// Fade out if a trace is active and this node isn't in the path
				!isHighlighted && "opacity-20 scale-95 pointer-events-none",
				// Apply Lens dimming
				lensOpacityClass,
			)}
		>
			{/* Input Handle (Left) - Hidden if no incoming edges, but ReactFlow handles that mostly */}
			<Handle
				type="target"
				position={Position.Left}
				className="w-3 h-3 bg-muted-foreground border-2 border-background"
			/>

			{/* Node Content */}
			<div className="p-4 flex flex-col gap-3">
				{/* Top Row: Icon & Name */}
				<div className="flex items-start gap-3">
					<div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted/50 border border-border/50">
						<PlatformIcon platform={data.platform} className="h-5 w-5" />
					</div>
					<div className="flex flex-col min-w-0 flex-1">
						<span
							className="font-semibold text-sm text-foreground truncate"
							title={data.label}
						>
							{data.label}
						</span>
						<span
							className="text-[10px] text-muted-foreground font-mono truncate"
							title={data.id}
						>
							{/* Show short platform name instead of full URN for cleanliness */}
							{data.platform.toUpperCase()}
						</span>
					</div>
				</div>

				{/* Bottom Row: Badges & Poison Pills */}
				<div className="flex items-center justify-between mt-1">
					{/* Left: Sensitivity Badge */}
					<Badge
						variant="outline"
						className={cn(
							"text-[9px] px-1.5 py-0 uppercase font-mono tracking-wider",
							data.sensitivity === "RESTRICTED" &&
								"text-rose-500 border-rose-500/20 bg-rose-500/5",
							data.sensitivity === "CONFIDENTIAL" &&
								"text-amber-500 border-amber-500/20 bg-amber-500/5",
						)}
					>
						{data.sensitivity}
					</Badge>

					{/* Right: The Poison Pill Indicator */}
					{data.is_ai_restricted && (
						<div
							className="flex items-center gap-1 text-[10px] font-bold text-rose-500 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20 animate-pulse"
							title="Contains restrictive legal clauses (e.g., No AI Training)"
						>
							<ShieldAlert className="h-3 w-3" />
							<span>RESTRICTED</span>
						</div>
					)}
				</div>
			</div>

			{/* Output Handle (Right) */}
			<Handle
				type="source"
				position={Position.Right}
				className="w-3 h-3 bg-muted-foreground border-2 border-background"
			/>
		</div>
	);
}
