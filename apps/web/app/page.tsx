"use client";

import { useEffect, useState } from "react";
import { useAmbyteApi } from "@/hooks/use-ambyte-api";

interface AmbyteUser {
	user: {
		email: string;
	};
}

export default function DashboardPage() {
	const api = useAmbyteApi();
	const [userData, setUserData] = useState<AmbyteUser | null>(null);

	useEffect(() => {
		// This call triggers the backend JIT provisioning logic
		api("/auth/whoami")
			.then((data) => {
				console.log("Ambyte Identity:", data);
				setUserData(data);
			})
			.catch((err) => console.error("Handshake failed", err));
	}, [api]);

	if (!userData) return <div>Loading Ambyte Context...</div>;

	return <div>Welcome, {userData.user.email}</div>;
}
