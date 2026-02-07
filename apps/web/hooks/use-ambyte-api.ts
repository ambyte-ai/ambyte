import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

interface UseAmbyteApiOptions {
	/**
	 * Project ID to include in requests. When provided, will be sent as
	 * X-Ambyte-Project-Id header on all requests.
	 */
	projectId?: string | null;
}

export function useAmbyteApi(options: UseAmbyteApiOptions = {}) {
	const { getToken, orgId } = useAuth();
	const { projectId } = options;

	// This hook wraps fetch to automatically add headers
	const fetchWithAuth = useCallback(
		async (endpoint: string, fetchOptions: RequestInit = {}) => {
			// 1. Get the JWT from Clerk (cache-aware)
			const token = await getToken();

			if (!token) {
				throw new Error("No auth token available");
			}

			// 2. Prepare headers
			const headers = new Headers(fetchOptions.headers);
			headers.set("Authorization", `Bearer ${token}`);
			headers.set("Content-Type", "application/json");

			// Pass the Organization ID context if available (for multi-tenancy)
			if (orgId) {
				headers.set("X-Ambyte-Org-Id", orgId);
			}

			// Pass the Project ID if available
			if (projectId) {
				headers.set("X-Ambyte-Project-Id", projectId);
			}

			// 3. Execute
			const baseUrl = process.env.NEXT_PUBLIC_API_URL;
			const response = await fetch(`${baseUrl}${endpoint}`, {
				...fetchOptions,
				headers,
			});

			if (!response.ok) {
				// Handle 401s specifically if needed
				throw new Error(`API Error: ${response.statusText}`);
			}

			return response.json();
		},
		[getToken, orgId, projectId],
	);

	return fetchWithAuth;
}
