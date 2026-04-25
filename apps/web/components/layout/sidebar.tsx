"use client";

import {
	Activity,
	Database,
	GitBranch,
	LayoutDashboard,
	Settings,
	ShieldCheck,
	UploadCloud,
} from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
	{
		label: "Overview",
		items: [{ name: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
	},
	{
		label: "Policy Engine",
		items: [
			{ name: "Obligations", href: "/obligations", icon: ShieldCheck },
			{ name: "Ingest", href: "/ingest", icon: UploadCloud },
		],
	},
	{
		label: "Data Map",
		items: [
			{ name: "Inventory", href: "/resources", icon: Database },
			{ name: "Lineage", href: "/lineage", icon: GitBranch },
		],
	},
	{
		label: "Observability",
		items: [{ name: "Audit Logs", href: "/audit", icon: Activity }],
	},
	{
		label: "Settings",
		items: [{ name: "Project Settings", href: "/settings", icon: Settings }],
	},
];

export function Sidebar() {
	const pathname = usePathname();

	return (
		<div className="flex h-full flex-col py-4">
			{/* Logo Area */}
			<div className="px-6 mb-8 flex items-center gap-2">
				<Image 
					src="/ambyte-logo.png" 
					alt="Ambyte Logo" 
					width={24} 
					height={24} 
					className="rounded"
				/>
				<span className="text-lg font-bold tracking-tight">Ambyte</span>
			</div>

			{/* Navigation Groups */}
			<div className="flex-1 space-y-6 px-4">
				{NAV_ITEMS.map((group) => (
					<div key={group.label}>
						<h3 className="mb-2 px-2 text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
							{group.label}
						</h3>
						<div className="space-y-1">
							{group.items.map((item) => {
								const isActive = pathname.startsWith(item.href);
								return (
									<Link
										key={item.href}
										href={item.href}
										className={cn(
											"flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
											isActive
												? "bg-primary/10 text-primary hover:bg-primary/15"
												: "text-muted-foreground hover:bg-accent hover:text-foreground",
										)}
									>
										<item.icon className="h-4 w-4" />
										{item.name}
									</Link>
								);
							})}
						</div>
					</div>
				))}
			</div>

			{/* Footer / Version */}
			<div className="px-6 py-4 border-t border-border/50">
				<p className="text-xs text-muted-foreground font-mono">{process.env.NEXT_PUBLIC_APP_VERSION || "v0.1.0"}</p>
			</div>
		</div>
	);
}
