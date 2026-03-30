"use client";

import {
    Background,
    BackgroundVariant,
    Controls,
    MiniMap,
    ReactFlow,
    type NodeMouseHandler,
    useReactFlow,
    Panel,
} from "@xyflow/react";
import { Loader2, ShieldAlert } from "lucide-react";
import { useEffect } from "react";

// CSS required by React Flow
import "@xyflow/react/dist/style.css";

// Ambyte Imports
import { useLineageGraph } from "@/hooks/use-lineage";
import { getLayoutedElements } from "@/lib/graph-layout";
import { useLineageStore } from "@/hooks/use-lineage-store";

// Custom Nodes & Edges
import { AnimatedRunEdge } from "./edges/AnimatedRunEdge";
import { ModelNode } from "./nodes/ModelNode";
import { ResourceNode } from "./nodes/ResourceNode";

// -----------------------------------------------------------------------------
// 1. Type Registrations
// Must be defined OUTSIDE the component to prevent React Flow from re-mounting
// nodes on every render cycle.
// -----------------------------------------------------------------------------
const nodeTypes = {
    resourceNode: ResourceNode,
    modelNode: ModelNode,
};

const edgeTypes = {
    runEdge: AnimatedRunEdge,
};

// -----------------------------------------------------------------------------
// 2. The Inner Flow Component
// -----------------------------------------------------------------------------
function Flow() {
    // A. Data Fetching
    // Lookback 30 days by default to keep the graph relevant
    const { graph, isLoading, isError } = useLineageGraph(30);

    // B. Global Store
    const {
        nodes,
        edges,
        onNodesChange,
        onEdgesChange,
        setGraphElements,
        setSelectedNodeId,
        clearTrace,
    } = useLineageStore();

    // C. React Flow Instance (for camera controls)
    const { fitView } = useReactFlow();

    // D. Auto-Layout & State Sync
    // When the API returns new data, run it through Dagre and push to Zustand
    useEffect(() => {
        if (graph && graph.nodes.length > 0) {
            // Calculate X/Y coordinates mathematically (Left to Right)
            const { nodes: layoutedNodes, edges: layoutedEdges } =
                getLayoutedElements(graph.nodes, graph.edges, "LR");

            setGraphElements(layoutedNodes, layoutedEdges);

            // Give React Flow a tick to render the new coordinates, then center the camera
            setTimeout(() => {
                fitView({ padding: 0.2, duration: 800 });
            }, 50);
        }
    }, [graph, setGraphElements, fitView]);

    // E. Event Handlers
    const handleNodeClick: NodeMouseHandler = (_, node) => {
        setSelectedNodeId(node.id);
    };

    const handlePaneClick = () => {
        // Clicking the empty canvas clears the selection and any active threat traces
        clearTrace();
    };

    // F. Loading & Error States
    if (isLoading && nodes.length === 0) {
        return (
            <div className="flex h-full w-full flex-col items-center justify-center bg-zinc-950/50">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mb-4" />
                <p className="text-sm font-mono text-muted-foreground animate-pulse">
                    Constructing compliance topology...
                </p>
            </div>
        );
    }

    if (isError) {
        return (
            <div className="flex h-full w-full flex-col items-center justify-center bg-rose-950/10">
                <ShieldAlert className="h-10 w-10 text-rose-500 mb-4" />
                <p className="text-sm font-semibold text-rose-500">
                    Failed to load lineage graph
                </p>
                <p className="text-xs text-muted-foreground mt-2 max-w-sm text-center">
                    Ensure your Ambyte Control Plane is reachable and the Lineage
                    extraction connectors have been run.
                </p>
            </div>
        );
    }

    // G. Render Canvas
    return (
        <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            onPaneClick={handlePaneClick}
            // Dark mode aesthetics
            colorMode="dark"
            minZoom={0.1}
            maxZoom={2}
            defaultEdgeOptions={{
                type: "runEdge",
                animated: true,
            }}
            // Disable default drag connection since lineage is read-only here
            nodesConnectable={false}
            elementsSelectable={true}
            className="bg-[#09090b]" // Exact tailwind zinc-950 to match the app
        >
            {/* Grid Background */}
            <Background
                color="#27272a" // zinc-800
                variant={BackgroundVariant.Dots}
                gap={24}
                size={2}
            />

            {/* Navigation Controls (Bottom Left) */}
            <Controls
                className="bg-card border-border fill-muted-foreground text-muted-foreground shadow-xl"
                showInteractive={false}
            />

            {/* Minimap (Bottom Right) */}
            <MiniMap
                nodeColor={(node) => {
                    // Color the minimap nodes based on their type to make it legible zoomed out
                    if (node.type === "modelNode") return "#8b5cf6"; // violet-500
                    if (node.data?.is_ai_restricted) return "#f43f5e"; // rose-500 (Poison Pill)
                    return "#3f3f46"; // zinc-700
                }}
                maskColor="#09090b80"
                className="bg-card border-border shadow-xl rounded-lg overflow-hidden"
            />

            {/* Optional: Add a watermark or legend panel here */}
            <Panel position="bottom-center" className="mb-4 pointer-events-none">
                <div className="px-3 py-1.5 rounded-full bg-background/80 border border-border shadow-lg backdrop-blur-sm text-[10px] font-mono text-muted-foreground">
                    Data Lineage & Risk Propagation
                </div>
            </Panel>
        </ReactFlow>
    );
}

// -----------------------------------------------------------------------------
// 3. Export
// -----------------------------------------------------------------------------
export function LineageCanvas() {
    return (
        <div className="h-full w-full relative border border-border/50 rounded-xl overflow-hidden shadow-2xl">
            <Flow />
        </div>
    );
}