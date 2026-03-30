import { create } from "zustand";
import {
    type Edge,
    type Node,
    type OnNodesChange,
    type OnEdgesChange,
    applyNodeChanges,
    applyEdgeChanges,
} from "@xyflow/react";

// -----------------------------------------------------------------------------
// Types & Enums
// -----------------------------------------------------------------------------

export type LineageLens = "DEFAULT" | "PRIVACY" | "AI_RISK" | "GEO";

interface LineageState {
    // 1. React Flow Standard State
    nodes: Node[];
    edges: Edge[];

    // 2. Ambyte Interactive State
    selectedNodeId: string | null;
    highlightedPath: string[]; // Array of URNs (nodes) and run_ids (edges) to illuminate
    activeLens: LineageLens;
    searchQuery: string;

    // 3. Actions (Mutators)
    // Standard React Flow handlers (required for dragging/selecting)
    onNodesChange: OnNodesChange;
    onEdgesChange: OnEdgesChange;

    // Custom Ambyte Handlers
    setGraphElements: (nodes: Node[], edges: Edge[]) => void;
    setSelectedNodeId: (id: string | null) => void;
    setHighlightedPath: (path: string[]) => void;
    setActiveLens: (lens: LineageLens) => void;
    setSearchQuery: (query: string) => void;
    clearTrace: () => void; // Utility to clear highlights and selections
}

// -----------------------------------------------------------------------------
// Store Implementation
// -----------------------------------------------------------------------------

export const useLineageStore = create<LineageState>((set, get) => ({
    // Initial State
    nodes: [],
    edges: [],
    selectedNodeId: null,
    highlightedPath: [],
    activeLens: "DEFAULT",
    searchQuery: "",

    // React Flow: Handle node dragging, selection, and deletion automatically
    onNodesChange: (changes) => {
        set({
            nodes: applyNodeChanges(changes, get().nodes),
        });
    },

    // React Flow: Handle edge selection automatically
    onEdgesChange: (changes) => {
        set({
            edges: applyEdgeChanges(changes, get().edges),
        });
    },

    // Ambyte: Populate the graph from the API (after running it through Dagre for layout)
    setGraphElements: (nodes, edges) => {
        set({ nodes, edges });
    },

    // Ambyte: Triggered when a user clicks a node (opens the Inspector Drawer)
    setSelectedNodeId: (id) => {
        set({ selectedNodeId: id });
    },

    // Ambyte: Triggers the "Crimson Trace" or upstream highlight animation
    setHighlightedPath: (path) => {
        set({ highlightedPath: path });
    },

    // Ambyte: Switches the visual language (e.g., highlights all PII nodes)
    setActiveLens: (lens) => {
        set({ activeLens: lens });
    },

    // Ambyte: For the HUD search bar to find and center specific URNs
    setSearchQuery: (query) => {
        set({ searchQuery: query });
    },

    // Ambyte: Reset view back to normal
    clearTrace: () => {
        set({
            selectedNodeId: null,
            highlightedPath: [],
            searchQuery: "",
        });
    },
}));