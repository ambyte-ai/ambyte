import { redirect } from "next/navigation";

export default function SettingsRootPage() {
	// Automatically redirect the base /settings route to the first tab
	redirect("/settings/general");
}
