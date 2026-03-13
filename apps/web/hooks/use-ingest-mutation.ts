import { useAuth } from "@clerk/nextjs";
import { useCallback, useState } from "react";
import { useProject } from "@/context/project-context";
import type { IngestJob } from "@/hooks/use-ingest-jobs";

interface UseIngestMutationResult {
    uploadFile: (file: File) => Promise<IngestJob>;
    isUploading: boolean;
    error: Error | null;
}

export function useIngestMutation(): UseIngestMutationResult {
    const { getToken, orgId } = useAuth();
    const { projectId } = useProject();

    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<Error | null>(null);

    const uploadFile = useCallback(
        async (file: File): Promise<IngestJob> => {
            setIsUploading(true);
            setError(null);

            try {
                // 1. Validate Context
                if (!projectId) {
                    throw new Error("No active project selected. Please select a project first.");
                }

                if (file.type !== "application/pdf") {
                    throw new Error("Invalid file type. Only PDF documents are supported.");
                }

                // 2. Prepare Authentication
                const token = await getToken();
                if (!token) {
                    throw new Error("Authentication token is missing. Please log in again.");
                }

                // 3. Construct FormData (Multipart Payload)
                const formData = new FormData();
                formData.append("file", file);
                formData.append("project_id", projectId);

                // 4. Prepare Headers
                // NOTE: We specifically DO NOT set Content-Type here.
                // The browser will automatically set 'multipart/form-data; boundary=...'
                const headers = new Headers();
                headers.set("Authorization", `Bearer ${token}`);

                if (orgId) {
                    headers.set("X-Ambyte-Org-Id", orgId);
                }
                headers.set("X-Ambyte-Project-Id", projectId);

                // 5. Execute Request
                const baseUrl = process.env.NEXT_PUBLIC_INGEST_API_URL || "http://127.0.0.1:8001";

                // Ensure no double slashes if baseUrl ends with /v1
                const endpoint = baseUrl.endsWith("/v1") ? "/ingest" : "/v1/ingest";

                const response = await fetch(`${baseUrl}${endpoint}`, {
                    method: "POST",
                    headers,
                    body: formData,
                });

                // 6. Handle Response
                if (!response.ok) {
                    // Attempt to parse standard FastAPI validation errors or custom error details
                    let errorMessage = response.statusText;
                    try {
                        const errorData = await response.json();
                        errorMessage = errorData.detail || errorMessage;
                    } catch {
                        // Ignored, fallback to statusText
                    }
                    throw new Error(`Upload failed: ${errorMessage}`);
                }

                const data: IngestJob = await response.json();
                return data;

            } catch (err) {
                const errorObj = err instanceof Error ? err : new Error("An unknown error occurred during upload.");
                setError(errorObj);
                throw errorObj; // Re-throw so the component can also handle it (e.g., show a toast)
            } finally {
                setIsUploading(false);
            }
        },
        [getToken, orgId, projectId]
    );

    return {
        uploadFile,
        isUploading,
        error,
    };
}