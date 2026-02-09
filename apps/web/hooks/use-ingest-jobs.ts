import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export type IngestStatus =
    | "QUEUED"
    | "PARSING"
    | "CHUNKING"
    | "EMBEDDING"
    | "DEFINING"
    | "EXTRACTION"
    | "MERGING"
    | "SYNCING"
    | "COMPLETED"
    | "FAILED";

export interface IngestJob {
    job_id: string;
    status: IngestStatus;
    message?: string;
    stats: {
        // Common stats populated by the worker
        filename?: string;
        duration_seconds?: number;
        chunks_processed?: number;
        final_obligations_count?: number;
        definitions_found?: number;
        [key: string]: any;
    };
}

// -----------------------------------------------------------------------------
// Hook
// -----------------------------------------------------------------------------

export function useIngestJobs(limit = 20) {
    const { projectId } = useProject();
    const api = useProjectApi();

    const key = projectId ? [`/ingest/jobs`, projectId, limit] : null;

    const fetcher = async () => {
        if (!projectId) return [];
        // The useProjectApi hook automatically injects the Project ID header
        return api(`/ingest/jobs?limit=${limit}`);
    };

    const { data, error, isLoading, mutate } = useSWR<IngestJob[]>(key, fetcher, {
        // Poll every 3 seconds to animate progress bars in the UI
        refreshInterval: 3000,
        // Revalidate immediately when window gains focus
        revalidateOnFocus: true,
        // Keep data fresh
        dedupingInterval: 1000,
    });

    return {
        jobs: data || [],
        isLoading,
        isError: !!error,
        refresh: mutate,
    };
}