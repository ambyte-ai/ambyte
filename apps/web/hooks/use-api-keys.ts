import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";
import type {
	ApiKey,
	ApiKeySecret,
	CreateApiKeyPayload,
} from "@/types/settings";

export function useApiKeys() {
	const { projectId } = useProject();
	const api = useProjectApi();

	// The API endpoint requires the project ID in the path
	const endpoint = projectId ? `/projects/${projectId}/keys` : null;

	// ===========================================================================
	// Queries (Fetching)
	// ===========================================================================
	const { data, error, isLoading, mutate } = useSWR<ApiKey[]>(
		endpoint,
		(url) => api(url),
		{
			revalidateOnFocus: false, // API Keys don't change often, save network calls
		},
	);

	// ===========================================================================
	// Mutations
	// ===========================================================================

	/**
	 * Generates a new API key.
	 * Returns the raw secret (sk_live_...) which must be shown to the user immediately.
	 */
	const createKey = async (
		payload: CreateApiKeyPayload,
	): Promise<ApiKeySecret> => {
		if (!projectId) throw new Error("No active project selected.");

		const result: ApiKeySecret = await api(`/projects/${projectId}/keys`, {
			method: "POST",
			body: JSON.stringify(payload),
		});

		// Optimistically update the UI by prepending the newly created key metadata
		// We pass `false` to avoid an immediate re-fetch since we know the new state
		mutate((currentKeys = []) => [result.info, ...currentKeys], false);

		return result;
	};

	/**
	 * Immediately revokes and deletes an API key.
	 */
	const revokeKey = async (keyId: string): Promise<void> => {
		if (!projectId) throw new Error("No active project selected.");

		await api(`/projects/${projectId}/keys/${keyId}`, {
			method: "DELETE",
		});

		// Optimistically remove the key from the UI
		mutate(
			(currentKeys = []) => currentKeys.filter((k) => k.id !== keyId),
			false,
		);
	};

	return {
		keys: data || [],
		isLoading,
		isError: !!error,
		error,
		createKey,
		revokeKey,
		refresh: mutate,
	};
}
