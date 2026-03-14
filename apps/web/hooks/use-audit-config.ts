import useSWR from "swr";
import { useAmbyteApi } from "@/hooks/use-ambyte-api";
import type { PublicKeyResponse } from "@/types/settings";

/**
 * Fetches the Ed25519 public key used to verify audit block signatures.
 * This is a system-wide (non-project-scoped) endpoint.
 */
export function usePublicKey() {
	const api = useAmbyteApi();

	const { data, error, isLoading } = useSWR<PublicKeyResponse>(
		"/audit/public-key",
		(url) => api(url),
		{
			revalidateOnFocus: false,
			dedupingInterval: 60_000, // The public key rarely changes; dedupe for 60s
		},
	);

	return {
		publicKey: data?.public_key ?? null,
		isLoading,
		isError: !!error,
		error,
	};
}
