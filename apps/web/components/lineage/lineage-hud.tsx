"use client";

import { useReactFlow } from "@xyflow/react";
import { Brain, Filter, Search, ShieldAlert, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { type LineageLens, useLineageStore } from "@/hooks/use-lineage-store";

export function LineageHud() {
	// 1. Zustand Store
	const {
		activeLens,
		setActiveLens,
		nodes,
		setSelectedNodeId,
		highlightedPath,
		clearTrace,
	} = useLineageStore();

	// 2. React Flow instance (for camera manipulation)
	// Note: This component MUST be rendered inside a <ReactFlowProvider>
	const { setCenter, fitView } = useReactFlow();

	// 3. Local State
	const [searchQuery, setSearchQuery] = useState("");

	// -------------------------------------------------------------------------
	// Handlers
	// -------------------------------------------------------------------------

	const handleSearch = (e: React.FormEvent) => {
		e.preventDefault();
		if (!searchQuery.trim()) {
			fitView({ duration: 800, padding: 0.2 });
			return;
		}

		const query = searchQuery.toLowerCase();

		// Find node by ID (URN) or Label (Name)
		const targetNode = nodes.find(
			(n) =>
				n.id.toLowerCase().includes(query) ||
				n.data?.label?.toString().toLowerCase().includes(query),
		);

		if (targetNode) {
			// Select it (opens the drawer)
			setSelectedNodeId(targetNode.id);

			// Snap camera to it
			setCenter(targetNode.position.x, targetNode.position.y, {
				zoom: 1.2,
				duration: 800,
			});
		} else {
			toast.error("Node not found", {
				description: `No resource or model matches "${searchQuery}"`,
			});
		}
	};

	const handleClearTrace = () => {
		clearTrace();
		fitView({ duration: 800, padding: 0.2 });
	};

	// -------------------------------------------------------------------------
	// Render
	// -------------------------------------------------------------------------
	return (
		<div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center gap-2 w-full max-w-2xl px-4 pointer-events-none">
			{/* Main HUD Bar */}
			<div className="flex items-center gap-2 p-1.5 rounded-xl bg-background/80 backdrop-blur-xl border shadow-2xl pointer-events-auto w-full">
				{/* 1. Lens Selector */}
				<div className="shrink-0">
					<Select
						value={activeLens}
						onValueChange={(val) => setActiveLens(val as LineageLens)}
					>
						<SelectTrigger className="w-[160px] h-9 border-none bg-transparent shadow-none focus:ring-0">
							<Filter className="w-4 h-4 mr-2 text-muted-foreground" />
							<SelectValue placeholder="Select Lens" />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="DEFAULT">
								<div className="flex items-center gap-2">
									<div className="w-2 h-2 rounded-full bg-zinc-500" />
									Standard View
								</div>
							</SelectItem>
							<SelectItem value="AI_RISK">
								<div className="flex items-center gap-2 text-rose-500">
									<Brain className="w-3.5 h-3.5" />
									AI Risk Map
								</div>
							</SelectItem>
							<SelectItem value="PRIVACY">
								<div className="flex items-center gap-2 text-indigo-400">
									<ShieldAlert className="w-3.5 h-3.5" />
									Privacy Radar
								</div>
							</SelectItem>
						</SelectContent>
					</Select>
				</div>

				<div className="w-px h-6 bg-border mx-1" />

				{/* 2. Search Bar */}
				<form
					onSubmit={handleSearch}
					className="flex-1 relative flex items-center"
				>
					<Search className="absolute left-3 w-4 h-4 text-muted-foreground" />
					<Input
						value={searchQuery}
						onChange={(e) => setSearchQuery(e.target.value)}
						placeholder="Search by URN or table name... (Press Enter)"
						className="w-full h-9 pl-9 bg-transparent border-none shadow-none focus-visible:ring-0 placeholder:text-muted-foreground/50"
					/>
				</form>
			</div>

			{/* Active Trace Warning Banner */}
			{highlightedPath.length > 0 && (
				<div className="flex items-center gap-3 px-4 py-2 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-400 shadow-lg backdrop-blur-md pointer-events-auto animate-in slide-in-from-top-4 fade-in duration-300">
					<ShieldAlert className="w-4 h-4 animate-pulse" />
					<span className="text-xs font-medium tracking-wide uppercase">
						Active Compliance Trace
					</span>
					<div className="w-px h-3 bg-rose-500/30 mx-1" />
					<Button
						variant="ghost"
						size="sm"
						onClick={handleClearTrace}
						className="h-6 px-2 text-[10px] uppercase tracking-wider text-rose-400 hover:text-rose-300 hover:bg-rose-500/20"
					>
						<X className="w-3 h-3 mr-1" />
						Clear
					</Button>
				</div>
			)}
		</div>
	);
}
