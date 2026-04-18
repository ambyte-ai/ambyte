import { useMemo } from "react";
import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";
import type { AuditLog, Decision } from "@/types/audit";

export interface AuditLogFilters {
	limit?: number;
	actorId?: string;
	resourceUrn?: string;
	/**
	 * Client-side filter: The backend /v1/audit/ endpoint currently returns all decisions.
	 * We filter this in the hook so the UI feels instantaneous when toggling tabs.
	 */
	decision?: Decision | "ALL";
}

export function useAuditLogs(
	filters: AuditLogFilters = {},
	isLive: boolean = false,
) {
	const { projectId } = useProject();
	const api = useProjectApi();

	// 1. Construct Server-Side Query Params
	const queryParams = new URLSearchParams();

	// Default to a generous limit if we are doing client-side filtering
	const fetchLimit = filters.limit || 100;
	queryParams.set("limit", fetchLimit.toString());

	if (filters.actorId) {
		queryParams.set("actor_id", filters.actorId);
	}

	if (filters.resourceUrn) {
		queryParams.set("resource", filters.resourceUrn);
	}

	const queryString = queryParams.toString();
	const endpoint = `/audit/${queryString ? `?${queryString}` : ""}`;

	// SWR Key depends on endpoint + projectId
	const key = projectId ? [endpoint, projectId] : null;

	const fetcher = async () => {
		if (!projectId) return [];
		return api(endpoint);
	};

	// 2. Fetch Data with SWR
	const { data, error, isLoading, mutate, isValidating } = useSWR<AuditLog[]>(
		key,
		fetcher,
		{
			// If Live Tail is active, poll every 3 seconds
			refreshInterval: isLive ? 3000 : 0,
			keepPreviousData: true,
			revalidateOnFocus: isLive,
			dedupingInterval: isLive ? 1000 : 5000,
		},
	);

	// 3. Apply Client-Side Filters
	const filteredLogs = useMemo(() => {
		let logs = data || [];

		if (filters.decision && filters.decision !== "ALL") {
			logs = logs.filter((log) => log.decision === filters.decision);
		}

		return logs;
	}, [data, filters.decision]);

	return {
		logs: filteredLogs,
		isLoading,
		isValidating,
		isError: !!error,
		error,
		refresh: mutate,
	};
}
