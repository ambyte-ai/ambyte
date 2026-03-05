import useSWR from "swr";
import { useAuth } from "@clerk/nextjs";
import { useProject } from "@/context/project-context";
import type { IngestJob } from "@/hooks/use-ingest-jobs";

interface UseJobPollingResult {
    job: IngestJob | undefined;
    isLoading: boolean;
    isError: boolean;
    error: Error | null;
    isComplete: boolean;
    isFailed: boolean;
}

export function useJobPolling(jobId: string | null): UseJobPollingResult {
    const { getToken, orgId } = useAuth();
    const { projectId } = useProject();

    const key = jobId ? `/v1/ingest/${jobId}` : null;

    const fetcher = async (endpoint: string): Promise<IngestJob> => {
        const token = await getToken();
        const headers = new Headers({ Authorization: `Bearer ${token}` });
        if (orgId) headers.set("X-Ambyte-Org-Id", orgId);
        if (projectId) headers.set("X-Ambyte-Project-Id", projectId);

        // Point to the Ingest API port
        const baseUrl = process.env.NEXT_PUBLIC_INGEST_API_URL || "http://127.0.0.1:8001";
        const res = await fetch(`${baseUrl}${endpoint}`, { headers });

        if (!res.ok) throw new Error("Failed to fetch job status");
        return res.json();
    };

    const { data, error, isLoading } = useSWR<IngestJob>(key, fetcher, {
        // Dynamic Polling: 
        // If the job is done or failed, stop polling (return 0). 
        // Otherwise, check every 2 seconds (2000ms).
        refreshInterval: (jobData) => {
            if (!jobData) return 2000;
            if (jobData.status === "COMPLETED" || jobData.status === "FAILED") {
                return 0; // Halt polling
            }
            return 2000;
        },
        revalidateOnFocus: true,
        // Don't retry aggressively if the ID is just flat-out invalid (404)
        shouldRetryOnError: false,
    });

    const isComplete = data?.status === "COMPLETED";
    const isFailed = data?.status === "FAILED";

    return {
        job: data,
        isLoading: isLoading || (!data && !error && !!jobId),
        isError: !!error,
        error,
        isComplete,
        isFailed,
    };
}