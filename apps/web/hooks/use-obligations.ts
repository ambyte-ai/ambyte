import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";
import { type Obligation, EnforcementLevel } from "@/types/obligation";

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface UseObligationsFilters {
    /** Search by title or slug */
    query?: string;
    /** Filter by strictness */
    enforcement_level?: EnforcementLevel;
    include_inactive?: boolean;
}

// -----------------------------------------------------------------------------
// List Hook (Main)
// -----------------------------------------------------------------------------

export function useObligations(filters?: UseObligationsFilters) {
    const { projectId } = useProject();
    const api = useProjectApi();

    // Construct URL Search Params
    const queryParams = new URLSearchParams();

    if (filters?.query) {
        queryParams.set("query", filters.query);
    }

    if (filters?.enforcement_level !== undefined && filters.enforcement_level !== EnforcementLevel.UNSPECIFIED) {
        // The backend Pydantic model accepts the Integer value of the Enum
        queryParams.set("enforcement_level", filters.enforcement_level.toString());
    }

    if (filters?.include_inactive) {
        queryParams.set("include_inactive", "true");
    }

    const queryString = queryParams.toString();
    const endpoint = `/obligations/${queryString ? `?${queryString}` : ""}`;

    // SWR Key depends on endpoint (and thus filters) + projectId
    const key = projectId ? [endpoint, projectId] : null;

    const fetcher = async () => {
        if (!projectId) return [];
        return api(endpoint);
    };

    const { data, error, isLoading, mutate, isValidating } = useSWR<Obligation[]>(
        key,
        fetcher,
        {
            // UX: Keep showing previous list while filtering to prevent flicker
            keepPreviousData: true,
            revalidateOnFocus: false,
        }
    );

    return {
        obligations: data || [],
        isLoading,
        isValidating,
        isError: !!error,
        error,
        refresh: mutate,
    };
}

// -----------------------------------------------------------------------------
// Single Item Hook (Detail View / Deep Linking)
// -----------------------------------------------------------------------------

export function useObligation(slug?: string | null) {
    const { projectId } = useProject();
    const api = useProjectApi();

    const key = projectId && slug ? [`/obligations/${slug}`, projectId] : null;

    const fetcher = async () => {
        if (!projectId || !slug) return null;
        return api(`/obligations/${slug}`);
    };

    const { data, error, isLoading, mutate } = useSWR<Obligation>(
        key,
        fetcher,
        {
            revalidateOnFocus: false,
        }
    );

    return {
        obligation: data,
        isLoading,
        isError: !!error,
        error,
        refresh: mutate,
    };
}