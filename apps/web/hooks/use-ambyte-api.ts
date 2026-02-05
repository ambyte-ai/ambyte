import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

export function useAmbyteApi() {
	const { getToken, orgId } = useAuth();

	// This hook wraps fetch to automatically add headers
	const fetchWithAuth = useCallback(
		async (endpoint: string, options: RequestInit = {}) => {
			// 1. Get the JWT from Clerk (cache-aware)
			const token = await getToken();

			if (!token) {
				throw new Error("No auth token available");
			}

			// 2. Prepare headers
			const headers = new Headers(options.headers);
			headers.set("Authorization", `Bearer ${token}`);
			headers.set("Content-Type", "application/json");

			// Pass the Organization ID context if available (for multi-tenancy)
			// Note: Project ID would need to be handled by local state (e.g. Zustand/Context)
			if (orgId) {
				// You might need to map Clerk Org ID to Ambyte Org ID via /whoami first,
				// but for JIT provisioning, this helps. TODO
			}

			// 3. Execute
			const baseUrl = process.env.NEXT_PUBLIC_API_URL;
			const response = await fetch(`${baseUrl}${endpoint}`, {
				...options,
				headers,
			});

			if (!response.ok) {
				// Handle 401s specifically if needed
				throw new Error(`API Error: ${response.statusText}`);
			}

			return response.json();
		},
		[getToken, orgId],
	);

	return fetchWithAuth;
}
