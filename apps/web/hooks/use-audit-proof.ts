import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";
import type { AuditProof } from "@/types/audit";

export function useAuditProof(logId: string | null) {
	const { projectId } = useProject();
	const api = useProjectApi();

	// SWR Key - Only fetch if logId AND projectId are truthy (Lazy loading)
	const key = projectId && logId ? [`/audit/proof/${logId}`, projectId] : null;

	const fetcher = async () => {
		if (!projectId || !logId) return null;

		// Using the custom wrapper which injects X-Ambyte-Project-Id
		return api(`/audit/proof/${logId}`);
	};

	const { data, error, isLoading, mutate, isValidating } = useSWR<AuditProof>(
		key,
		fetcher,
		{
			// Cryptographic proofs are immutable once generated.
			// We don't need to poll or aggressively revalidate them.
			revalidateOnFocus: false,
			revalidateIfStale: false,
			// If it fails (e.g. 409 Conflict because the log isn't sealed into a block yet),
			// we don't want SWR to hammer the backend immediately.
			shouldRetryOnError: false,
		},
	);

	return {
		proof: data,
		isLoading,
		isValidating,
		isError: !!error,
		error,
		refresh: mutate,
	};
}
