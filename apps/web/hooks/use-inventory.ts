import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";

// -----------------------------------------------------------------------------
// Types (Mirroring ambyte_schemas.models.inventory & common)
// -----------------------------------------------------------------------------

export interface ResourceColumn {
    name: string;
    type: string;
    comment?: string | null;
    tags?: Record<string, string>;
}

export interface ResourceAttributes {
    tags?: Record<string, string>;
    owner?: string | null;
    table_type?: string;
    storage_location?: string;
    columns?: ResourceColumn[];
    hierarchy?: {
        catalog?: string;
        schema?: string;
        database?: string;
    };
    // Catch-all for other connector-specific metadata
    [key: string]: any;
}

export interface Resource {
    id: string;
    project_id: string;
    urn: string;
    platform: string;
    name: string | null;
    attributes: ResourceAttributes;
    created_at: string; // ISO 8601
    updated_at: string; // ISO 8601
}

export interface PaginatedResources {
    items: Resource[];
    total: number;
    page: number;
    size: number;
    pages: number;
}

export interface UseInventoryFilters {
    page?: number;
    size?: number;
    /** Filter by platform (e.g., 'snowflake', 'databricks', 'aws-s3') */
    platform?: string;
    /** Search by URN or Name */
    query?: string;
    /** Filter by sensitivity (e.g., 'RESTRICTED', 'CONFIDENTIAL') */
    sensitivity?: string;
}

// -----------------------------------------------------------------------------
// Hook
// -----------------------------------------------------------------------------

export function useInventory(filters?: UseInventoryFilters) {
    const { projectId } = useProject();
    const api = useProjectApi();

    // Construct URL Search Params
    const queryParams = new URLSearchParams();

    if (filters?.page) {
        queryParams.set("page", filters.page.toString());
    }

    if (filters?.size) {
        queryParams.set("size", filters.size.toString());
    }

    // Note: The backend GET /v1/resources/ currently supports pagination natively.
    // We pass these extra filters in the query string so the frontend is ready 
    // when the backend endpoint is updated to support server-side filtering. TODO
    if (filters?.platform && filters.platform !== "all") {
        queryParams.set("platform", filters.platform);
    }

    if (filters?.query) {
        queryParams.set("query", filters.query);
    }

    if (filters?.sensitivity && filters.sensitivity !== "all") {
        queryParams.set("sensitivity", filters.sensitivity);
    }

    const queryString = queryParams.toString();
    const endpoint = `/resources/${queryString ? `?${queryString}` : ""}`;

    // SWR Key depends on endpoint (and thus filters) + projectId
    const key = projectId ? [endpoint, projectId] : null;

    const fetcher = async () => {
        if (!projectId) return null;
        // The useProjectApi hook automatically injects the X-Ambyte-Project-Id header
        return api(endpoint);
    };

    const { data, error, isLoading, mutate, isValidating } =
        useSWR<PaginatedResources>(key, fetcher, {
            // UX: Keep showing previous list while fetching next page to prevent table flicker
            keepPreviousData: true,
            // Resources don't change fast enough to warrant aggressive revalidation
            revalidateOnFocus: false,
            dedupingInterval: 5000,
        });

    return {
        resources: data?.items || [],
        pagination: {
            total: data?.total || 0,
            page: data?.page || 1,
            size: data?.size || 50,
            pages: data?.pages || 0,
        },
        isLoading,
        isValidating,
        isError: !!error,
        error,
        refresh: mutate,
    };
}