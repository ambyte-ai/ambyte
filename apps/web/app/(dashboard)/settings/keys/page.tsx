import type { Metadata } from "next";
import { ApiKeyManager } from "@/components/settings/api-key-manager";

export const metadata: Metadata = {
	title: "API Keys | Settings | Ambyte",
	description:
		"Generate and manage machine credentials for the Ambyte SDK and CLI.",
};

export default function ApiKeysPage() {
	return (
		<div className="animate-in fade-in duration-500">
			{/* 
			  The ApiKeyManager encapsulates:
			  - SWR data fetching (useApiKeys hook)
			  - The Data Table (listing keys)
			  - The Create Key Modal (Form -> Result state flow)
			  - The Revoke Key Modal (Danger action)
			*/}
			<ApiKeyManager />
		</div>
	);
}
