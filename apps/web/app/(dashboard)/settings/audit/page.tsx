import type { Metadata } from "next";
import { AuditConfig } from "@/components/settings/audit-config";

export const metadata: Metadata = {
	title: "Audit & Security | Settings | Ambyte",
	description:
		"Cryptographic keys and verification tools for your immutable audit ledger.",
};

export default function AuditSettingsPage() {
	return (
		<div className="animate-in fade-in duration-500">
			<AuditConfig />
		</div>
	);
}
