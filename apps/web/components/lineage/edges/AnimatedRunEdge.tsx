import {
	BaseEdge,
	type Edge,
	EdgeLabelRenderer,
	type EdgeProps,
	getSmoothStepPath,
} from "@xyflow/react";
import { Activity, User } from "lucide-react";
import { useLineageStore } from "@/hooks/use-lineage-store";
import { cn } from "@/lib/utils";

// Define the expected shape of the edge data from the backend
interface RunEdgeData extends Record<string, unknown> {
	run_id: string;
	run_type: string;
	success: boolean;
	actor_id: string;
	start_time: string;
}

// Full edge type required by EdgeProps
type RunEdge = Edge<RunEdgeData>;

export function AnimatedRunEdge({
	id,
	source,
	target,
	sourceX,
	sourceY,
	targetX,
	targetY,
	sourcePosition,
	targetPosition,
	data,
	markerEnd,
}: EdgeProps<RunEdge>) {
	// 1. Calculate the SVG Path using React Flow's built-in SmoothStep math
	// This gives us nice right-angled pipes instead of direct straight lines.
	const [edgePath, labelX, labelY] = getSmoothStepPath({
		sourceX,
		sourceY,
		sourcePosition,
		targetX,
		targetY,
		targetPosition,
		borderRadius: 16,
	});

	// 2. Connect to Zustand Store to check visibility state
	const { highlightedPath, activeLens } = useLineageStore();

	// 3. Determine Edge State
	const hasActiveTrace = highlightedPath.length > 0;

	// An edge is part of the "Crimson Trace" if BOTH its source and target are in the path
	const isHighlighted =
		hasActiveTrace &&
		highlightedPath.includes(source) &&
		highlightedPath.includes(target);

	const isDimmed = hasActiveTrace && !isHighlighted;

	// 4. Determine Dynamic Styling
	// If the job failed, we might want it to look dashed and yellow.
	// If it's a poison trace, it glows red. Otherwise, subtle gray.
	let pathClass = "stroke-border transition-all duration-500";
	let strokeWidth = 2;

	if (isHighlighted) {
		pathClass =
			"stroke-rose-500 drop-shadow-[0_0_8px_rgba(244,63,94,0.6)] animate-pulse";
		strokeWidth = 3;
	} else if (!data?.success) {
		pathClass = "stroke-amber-500/50 stroke-dasharray-[5,5]";
	}

	if (isDimmed) {
		pathClass = cn(pathClass, "opacity-20");
	}

	// Format run type for display (e.g., "AI_TRAINING" -> "AI Training")
	const formatRunType = (type: string) => {
		if (!type) return "Data Flow";
		return type.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
	};

	return (
		<>
			{/* The Visible Edge */}
			<BaseEdge
				id={id}
				path={edgePath}
				markerEnd={markerEnd}
				style={{ strokeWidth }}
				className={pathClass}
			/>

			{/* Invisible Wider Edge (Makes hovering/clicking the line much easier) */}
			<path
				d={edgePath}
				fill="none"
				strokeOpacity={0}
				strokeWidth={20}
				className="cursor-pointer"
				onClick={() => console.log("Edge clicked:", data?.run_id)}
			/>

			{/* Custom Edge Label (The floating badge) */}
			<EdgeLabelRenderer>
				<div
					className={cn(
						"absolute pointer-events-auto transform -translate-x-1/2 -translate-y-1/2 transition-all duration-500 group cursor-pointer",
						isDimmed ? "opacity-20 pointer-events-none" : "opacity-100",
						// Elevated z-index so it floats above the lines
						"z-20",
					)}
					style={{
						// React Flow requires absolute positioning based on the calculated labelX/Y
						left: labelX,
						top: labelY,
					}}
				>
					{/* The default view: Small Badge */}
					<div
						className={cn(
							"flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-mono font-medium border shadow-sm backdrop-blur-md",
							isHighlighted
								? "bg-rose-500/10 border-rose-500/30 text-rose-400"
								: "bg-background/80 border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
						)}
					>
						<Activity className="h-3 w-3 shrink-0" />
						<span>{formatRunType(data?.run_type || "UNKNOWN")}</span>
					</div>

					{/* Tooltip that appears on Hover (shows Actor and Time) */}
					<div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-max opacity-0 scale-95 pointer-events-none group-hover:opacity-100 group-hover:scale-100 transition-all duration-200 z-30">
						<div className="bg-popover text-popover-foreground border border-border shadow-xl rounded-lg p-3 text-xs flex flex-col gap-2">
							<div className="font-semibold pb-1 border-b border-border/50">
								Execution Details
							</div>
							<div className="flex items-center gap-2">
								<User className="h-3.5 w-3.5 text-muted-foreground" />
								<span className="font-mono text-muted-foreground">Actor:</span>
								<span>{data?.actor_id || "System"}</span>
							</div>
							<div className="flex items-center gap-2">
								<Activity className="h-3.5 w-3.5 text-muted-foreground" />
								<span className="font-mono text-muted-foreground">Status:</span>
								<span
									className={
										data?.success ? "text-emerald-500" : "text-amber-500"
									}
								>
									{data?.success ? "Success" : "Failed"}
								</span>
							</div>
						</div>
					</div>
				</div>
			</EdgeLabelRenderer>
		</>
	);
}
