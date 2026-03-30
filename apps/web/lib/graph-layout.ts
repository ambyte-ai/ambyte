import dagre from "dagre";
import type { Edge as ReactFlowEdge, Node as ReactFlowNode } from "@xyflow/react";
import type { GraphEdge, GraphNode } from "@/hooks/use-lineage";

// -----------------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------------

// Estimated dimensions of our custom Ambyte nodes. 
// We make them wide enough to fit URNs, Icons, and Governance Badges.
const NODE_WIDTH = 280;
const NODE_HEIGHT = 100;

// Spacing between nodes
const RANK_SEP = 150; // Horizontal distance between layers (columns)
const NODE_SEP = 50;  // Vertical distance between nodes in the same layer

/**
 * Transforms backend API data into layouted React Flow elements.
 * 
 * @param apiNodes The nodes from the Ambyte Control Plane
 * @param apiEdges The edges (runs) from the Ambyte Control Plane
 * @param direction "LR" (Left-to-Right) or "TB" (Top-to-Bottom)
 * @returns Object containing React Flow compatible nodes and edges with X/Y coordinates
 */
export function getLayoutedElements(
    apiNodes: GraphNode[],
    apiEdges: GraphEdge[],
    direction: "LR" | "TB" = "LR"
): { nodes: ReactFlowNode[]; edges: ReactFlowEdge[] } {
    // 1. Initialize the Dagre graph
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));

    // Configure the layout algorithm
    dagreGraph.setGraph({
        rankdir: direction,
        ranksep: RANK_SEP,
        nodesep: NODE_SEP,
        edgesep: 50,
    });

    // 2. Map API Nodes -> React Flow Nodes AND add to Dagre
    const rfNodes: ReactFlowNode[] = apiNodes.map((node) => {
        // Map backend 'node_type' to the specific React Component we will register
        const rfType = node.node_type === "model" ? "modelNode" : "resourceNode";

        // Register node with Dagre so it knows the dimensions for math
        dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });

        return {
            id: node.id,
            type: rfType,
            // Position is a placeholder; it will be overwritten after dagre.layout()
            position: { x: 0, y: 0 },
            // We pass the entire API object into the 'data' payload so our custom 
            // React components have access to all the governance metadata.
            data: { ...node },
        };
    });

    // 3. Map API Edges -> React Flow Edges AND add to Dagre
    const rfEdges: ReactFlowEdge[] = apiEdges.map((edge) => {
        // Register edge with Dagre to define the relationships
        dagreGraph.setEdge(edge.source, edge.target);

        return {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            type: "runEdge", // Custom edge component we will build
            // Optional: if the run failed, we might want it to look different
            animated: edge.success,
            data: {
                run_id: edge.run_id,
                run_type: edge.run_type,
                success: edge.success,
                actor_id: edge.actor_id,
                start_time: edge.start_time,
            },
        };
    });

    // 4. Execute Layout Math
    // This synchronously calculates the X and Y for every node in the dagreGraph
    dagre.layout(dagreGraph);

    // 5. Apply Coordinates back to React Flow nodes
    const layoutedNodes = rfNodes.map((node) => {
        const nodeWithPosition = dagreGraph.node(node.id);

        // Dagre returns the (x, y) of the *center* of the node.
        // React Flow requires the (x, y) of the *top-left* corner.
        const targetX = nodeWithPosition.x - NODE_WIDTH / 2;
        const targetY = nodeWithPosition.y - NODE_HEIGHT / 2;

        return {
            ...node,
            position: { x: targetX, y: targetY },
            // React Flow specific: ensure the node renders on top of the edges
            zIndex: 10,
        };
    });

    return { nodes: layoutedNodes, edges: rfEdges };
}