import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useAmbyteApi } from "@/hooks/use-ambyte-api";

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
    const api = useAmbyteApi();

    const key = projectId ? [`/resources/risks`, projectId, limit] : null;

    const fetcher = async () => {
        if (!projectId) return [];

        // Pass project context via header as required by backend stats endpoint
        return api(`/resources/risks?limit=${limit}`, {
            headers: {
                "X-Ambyte-Project-Id": projectId,
            },
        });
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