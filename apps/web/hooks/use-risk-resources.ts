import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";

export interface ResourceRiskItem {
    urn: string;
    name: string;
    platform: string;
    sensitivity: string;
    risk_level: string;
    owner?: string;
}

export function useRiskResources(limit: number = 10) {
    const { projectId } = useProject();
    const api = useProjectApi();

    const key = projectId ? [`/resources/risks`, projectId, limit] : null;

    const fetcher = async () => {
        if (!projectId) return [];

        // Project ID header is automatically injected by useProjectApi
        return api(`/resources/risks?limit=${limit}`);
    };

    const { data, error, isLoading, mutate } = useSWR<ResourceRiskItem[]>(
        key,
        fetcher,
        {
            refreshInterval: 60000, // Refresh every minute
            revalidateOnFocus: false,
        }
    );

    return {
        resources: data,
        isLoading,
        isError: !!error,
        refresh: mutate,
    };
}