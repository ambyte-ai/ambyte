import type { Metadata } from "next";
import { MemberManager } from "@/components/settings/member-manager";

export const metadata: Metadata = {
	title: "Team Access | Settings | Ambyte",
	description: "Manage who has access to this project and what they can do.",
};

export default function TeamSettingsPage() {
	return (
		<div className="animate-in fade-in duration-500">
			<MemberManager />
		</div>
	);
}
