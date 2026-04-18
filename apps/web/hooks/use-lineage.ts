import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";

// -----------------------------------------------------------------------------
// Types (Mirroring Python Schemas from lineage.py)
// -----------------------------------------------------------------------------

export interface GraphNode {
	id: string;
	label: string;
	platform: string;
	node_type: "resource" | "model";
	sensitivity: string;
	risk_level: string;
	tags: Record<string, string>;
	is_ai_restricted: boolean;
}

export interface GraphEdge {
	id: string;
	source: string;
	target: string;
	run_id: string;
	run_type: string;
	success: boolean;
	actor_id: string | null;
	start_time: string | null; // ISO 8601 string
}

export interface LineageGraphResponse {
	nodes: GraphNode[];
	edges: GraphEdge[];
}

export interface LineageAnalysisResponse {
	target_urn: string;
	inherited_risk: string;
	inherited_sensitivity: string;
	poisoned_constraints: string[];
	upstream_path: string[];
}

// -----------------------------------------------------------------------------
// Hooks
// -----------------------------------------------------------------------------

/**
 * Fetches the complete Data Lineage topology for the React Flow canvas.
 * Includes nodes enriched with metadata (sensitivity, poison pills) and edges.
 */
export function useLineageGraph(lookbackDays: number = 30) {
	const { projectId } = useProject();
	const api = useProjectApi();

	// SWR Key depends on endpoint, project, and lookback window
	const key = projectId ? ["/lineage/graph", projectId, lookbackDays] : null;

	const fetcher = async () => {
		if (!projectId) return null;
		// The useProjectApi hook automatically injects the X-Ambyte-Project-Id header
		return api(`/lineage/graph?lookback_days=${lookbackDays}`);
	};

	const { data, error, isLoading, mutate, isValidating } =
		useSWR<LineageGraphResponse>(key, fetcher, {
			// UX: Keep previous graph data visible while fetching updates to prevent canvas flickering
			keepPreviousData: true,
			// UX: Do not aggressively revalidate the graph on window focus, as re-rendering
			// a large DAG is expensive and resets user zoom/pan state.
			revalidateOnFocus: false,
			dedupingInterval: 10000,
		});

	return {
		graph: data || { nodes: [], edges: [] },
		isLoading,
		isValidating,
		isError: !!error,
		error,
		refresh: mutate,
	};
}

/**
 * Fetches the diagnostic compliance trace for a specific node.
 * Used by the Inspector Drawer to show inherited risk and map "Poison Pills".
 *
 * @param urn The Unique Resource Name to analyze. Pass null to disable fetching.
 */
export function useLineageAnalysis(urn: string | null) {
	const { projectId } = useProject();
	const api = useProjectApi();

	// SWR Key - Only fetch if URN is provided
	const key = projectId && urn ? ["/lineage/analyze", projectId, urn] : null;

	const fetcher = async () => {
		if (!projectId || !urn) return null;
		// URNs contain special characters (:, /) so we must encode them for the URL path
		const encodedUrn = encodeURIComponent(urn);
		return api(`/lineage/analyze/${encodedUrn}`);
	};

	const { data, error, isLoading, mutate, isValidating } =
		useSWR<LineageAnalysisResponse>(key, fetcher, {
			revalidateOnFocus: false,
			// Cache the analysis for a decent amount of time so clicking back and forth
			// between nodes feels instantaneous.
			dedupingInterval: 30000,
		});

	return {
		analysis: data,
		isLoading,
		isValidating,
		isError: !!error,
		error,
		refresh: mutate,
	};
}
