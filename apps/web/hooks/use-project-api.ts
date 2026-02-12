import { useProject } from "@/context/project-context";
import { useAmbyteApi } from "@/hooks/use-ambyte-api";

/**
 * Convenience wrapper around useAmbyteApi that automatically injects
 * the current project ID from ProjectContext into all requests.
 *
 * Use this hook in any component that needs project-scoped API calls.
 * The X-Ambyte-Project-Id header will be automatically included.
 *
 * @example
 * const api = useProjectApi();
 * const data = await api("/stats/dashboard"); // Project ID header auto-injected
 */
export function useProjectApi() {
	const { projectId } = useProject();
	return useAmbyteApi({ projectId });
}
