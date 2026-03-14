import useSWR from "swr";
import { useProject } from "@/context/project-context";
import { useProjectApi } from "@/hooks/use-project-api";
import type {
	AddMemberPayload,
	ProjectMember,
	ProjectRole,
} from "@/types/settings";

export function useMembers() {
	const { projectId } = useProject();
	const api = useProjectApi();

	const endpoint = projectId ? `/projects/${projectId}/members` : null;

	// ===========================================================================
	// Queries (Fetching)
	// ===========================================================================
	const { data, error, isLoading, mutate } = useSWR<ProjectMember[]>(
		endpoint,
		(url) => api(url),
		{
			revalidateOnFocus: false,
		},
	);

	// ===========================================================================
	// Mutations
	// ===========================================================================

	/**
	 * Invites an existing organization user to the project.
	 */
	const addMember = async (
		payload: AddMemberPayload,
	): Promise<ProjectMember> => {
		if (!projectId) throw new Error("No active project selected.");

		const result: ProjectMember = await api(`/projects/${projectId}/members`, {
			method: "POST",
			body: JSON.stringify(payload),
		});

		mutate((current = []) => [...current, result], false);
		return result;
	};

	/**
	 * Changes a member's role within the project.
	 */
	const updateRole = async (
		userId: string,
		newRole: ProjectRole,
	): Promise<ProjectMember> => {
		if (!projectId) throw new Error("No active project selected.");

		const result: ProjectMember = await api(
			`/projects/${projectId}/members/${userId}`,
			{
				method: "PATCH",
				body: JSON.stringify({ role: newRole }),
			},
		);

		mutate(
			(current = []) => current.map((m) => (m.user_id === userId ? result : m)),
			false,
		);
		return result;
	};

	/**
	 * Removes a member from the project entirely.
	 */
	const removeMember = async (userId: string): Promise<void> => {
		if (!projectId) throw new Error("No active project selected.");

		await api(`/projects/${projectId}/members/${userId}`, {
			method: "DELETE",
		});

		mutate(
			(current = []) => current.filter((m) => m.user_id !== userId),
			false,
		);
	};

	return {
		members: data || [],
		isLoading,
		isError: !!error,
		error,
		addMember,
		updateRole,
		removeMember,
		refresh: mutate,
	};
}
