"use client";

import Link from "next/link";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { ChevronDown, FolderKanban, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useProject } from "@/context/project-context";

export function Header() {
	const { projects, projectId, setProjectId, isLoading } = useProject();

	const activeProject = projects.find((p) => p.id === projectId);
	const hasProjects = projects.length > 0;

	return (
		<header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-border bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
			<div className="flex items-center gap-4">
				{/* Org Switcher (Clerk) */}
				<OrganizationSwitcher
					hidePersonal={true}
					afterCreateOrganizationUrl="/dashboard"
					appearance={{
						elements: {
							rootBox: "flex items-center",
							organizationSwitcherTrigger:
								"h-9 px-3 border border-border rounded-md hover:bg-accent hover:text-accent-foreground transition-colors gap-2 text-sm font-medium",
						},
					}}
				/>

				<span className="text-muted-foreground/30 text-lg font-light">/</span>

				{/* Project Switcher (Custom) */}
				<DropdownMenu>
					<DropdownMenuTrigger asChild>
						<Button
							variant="outline"
							className={`h-9 gap-2 justify-between min-w-[200px] ${!hasProjects && !isLoading
									? "border-dashed text-muted-foreground"
									: ""
								}`}
							disabled={isLoading}
						>
							<div className="flex items-center gap-2">
								<FolderKanban className="h-4 w-4 text-muted-foreground" />
								<span>
									{isLoading
										? "Loading..."
										: activeProject?.name || (hasProjects ? "Select Project" : "No Projects")}
								</span>
							</div>
							<ChevronDown className="h-3 w-3 opacity-50" />
						</Button>
					</DropdownMenuTrigger>
					<DropdownMenuContent align="start" className="w-[200px]">
						{projects.map((p) => (
							<DropdownMenuItem
								key={p.id}
								onClick={() => setProjectId(p.id)}
								className="cursor-pointer"
							>
								{p.name}
							</DropdownMenuItem>
						))}
						{!hasProjects && (
							<div className="p-2 text-xs text-muted-foreground text-center">
								No projects in this organization
							</div>
						)}
						{hasProjects && <DropdownMenuSeparator />}
						<DropdownMenuItem asChild>
							<Link
								href="/projects/new"
								className="flex items-center gap-2 cursor-pointer"
							>
								<Plus className="h-4 w-4" />
								Create Project
							</Link>
						</DropdownMenuItem>
					</DropdownMenuContent>
				</DropdownMenu>
			</div>

			<div className="flex items-center gap-4">
				<UserButton afterSignOutUrl="/sign-in" />
			</div>
		</header>
	);
}
