"use client";

import { Key, Settings, ShieldCheck, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const sidebarNavItems = [
	{
		title: "General",
		href: "/settings/general",
		icon: Settings,
	},
	{
		title: "API Keys",
		href: "/settings/keys",
		icon: Key,
	},
	{
		title: "Team Access",
		href: "/settings/team",
		icon: Users,
	},
	{
		title: "Audit & Security",
		href: "/settings/audit",
		icon: ShieldCheck,
	},
];

export default function SettingsLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	const pathname = usePathname();

	return (
		<div className="flex flex-col gap-8 animate-in fade-in duration-500 h-full">
			{/* Settings Header */}
			<div>
				<h1 className="text-2xl font-bold tracking-tight text-foreground">
					Project Settings
				</h1>
				<p className="text-sm text-muted-foreground mt-1">
					Manage your workspace details, API keys, and team access.
				</p>
			</div>

			<Separator className="bg-border/50" />

			{/* Main Layout Grid */}
			<div className="flex flex-col md:flex-row gap-8 lg:gap-12">
				{/* Vertical Sidebar Navigation */}
				<aside className="w-full md:w-56 lg:w-64 shrink-0 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0">
					<nav className="flex md:flex-col gap-1.5 min-w-max md:min-w-0">
						{sidebarNavItems.map((item) => {
							const isActive = pathname.startsWith(item.href);
							return (
								<Link
									key={item.href}
									href={item.href}
									className={cn(
										"flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
										isActive
											? "bg-zinc-800/50 text-foreground shadow-sm ring-1 ring-border/50"
											: "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
									)}
								>
									<item.icon
										className={cn(
											"h-4 w-4 shrink-0 transition-colors",
											isActive ? "text-indigo-400" : "opacity-70",
										)}
									/>
									<span className="whitespace-nowrap">{item.title}</span>
								</Link>
							);
						})}
					</nav>
				</aside>

				{/* Settings Content Area */}
				{/* max-w-4xl keeps forms readable on ultra-wide monitors */}
				<main className="flex-1 max-w-4xl min-w-0 pb-12">{children}</main>
			</div>
		</div>
	);
}
