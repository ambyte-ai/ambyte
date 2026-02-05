import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useAmbyteApi } from "@/hooks/use-ambyte-api";

// -----------------------------------------------------------------------------
// Types (Mirroring src/schemas/stats.py)
// -----------------------------------------------------------------------------

export interface DashboardKPI {
	total_requests_24h: number;
	denied_requests_24h: number;
	enforcement_rate_24h: number;
	active_obligations: number;
	protected_resources: number;
	// Note: pending_ingestions isn't in backend yet, handled via separate logic or future update
	// TODO: Add pending_ingestions
}

export interface TrafficPoint {
	timestamp: string; // ISO 8601
	allowed_count: number;
	denied_count: number;
}

export interface DenyReasonAgg {
	reason: string;
	count: number;
}

export interface RecentBlock {
	id: string;
	timestamp: string;
	actor_id: string;
	action: string;
	resource_urn: string;
	reason_summary: string | null;
}

export interface DashboardStatsResponse {
	kpi: DashboardKPI;
	traffic_series: TrafficPoint[];
	top_deny_reasons: DenyReasonAgg[];
	recent_blocks: RecentBlock[];
}

// -----------------------------------------------------------------------------
// Hook
// -----------------------------------------------------------------------------

export function useDashboardStats(lookbackHours: number = 24) {
	const { projectId } = useProject();
	const api = useAmbyteApi();

	// Key depends on projectId to auto-refetch on context switch
	const key = projectId ? [`/stats/dashboard`, projectId, lookbackHours] : null;

	const fetcher = async () => {
		if (!projectId) return null;

		// The API client automatically injects the Bearer token.
		// We need to inject the X-Ambyte-Project-Id header specifically for this call
		// because the backend stats endpoint relies on it for context.
		return api(`/stats/dashboard?lookback_hours=${lookbackHours}`, {
			headers: {
				"X-Ambyte-Project-Id": projectId,
			},
		});
	};

	const { data, error, isLoading, mutate } = useSWR<DashboardStatsResponse>(
		key,
		fetcher,
		{
			// Auto-refresh every 30s for a "Live" feel
			refreshInterval: 30000,
			revalidateOnFocus: true,
			// Don't retry if project ID is missing/invalid (400/404)
			shouldRetryOnError: false,
		},
	);

	return {
		stats: data,
		isLoading,
		isError: !!error,
		error,
		refresh: mutate,
	};
}
