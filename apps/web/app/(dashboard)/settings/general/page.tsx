"use client";

import { AlertTriangle, Check, Copy, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardFooter,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useProject } from "@/context/project-context";
import { useAmbyteApi } from "@/hooks/use-ambyte-api";

export default function GeneralSettingsPage() {
	const { projects, projectId, refreshContext } = useProject();
	const api = useAmbyteApi({ projectId });

	const activeProject = projects.find((p) => p.id === projectId);

	// State
	const [projectName, setProjectName] = useState("");
	const [isSaving, setIsSaving] = useState(false);
	const [isCopied, setIsCopied] = useState(false);

	// Danger Zone State
	const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
	const [deleteConfirmation, setDeleteConfirmation] = useState("");
	const [isDeleting, setIsDeleting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// Sync local state when the active project context changes
	useEffect(() => {
		if (activeProject) {
			setProjectName(activeProject.name);
		}
	}, [activeProject]);

	// Prevent rendering if context hasn't loaded yet
	if (!activeProject) {
		return (
			<div className="flex items-center justify-center h-64">
				<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	const hasChanges = projectName.trim() !== activeProject.name;

	// ---------------------------------------------------------------------------
	// Handlers
	// ---------------------------------------------------------------------------

	const handleCopyId = async () => {
		if (!projectId) return;
		await navigator.clipboard.writeText(projectId);
		setIsCopied(true);
		setTimeout(() => setIsCopied(false), 2000);
	};

	const handleSaveName = async () => {
		if (!projectName.trim() || !hasChanges) return;

		setIsSaving(true);
		setError(null);

		try {
			await api(`/projects/${projectId}`, {
				method: "PATCH",
				body: JSON.stringify({ name: projectName.trim() }),
			});
			// Refresh global context so the sidebar/header updates
			await refreshContext();
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to update project");
		} finally {
			setIsSaving(false);
		}
	};

	const handleDeleteProject = async () => {
		if (deleteConfirmation !== activeProject.name) return;

		setIsDeleting(true);
		setError(null);

		try {
			await api(`/projects/${projectId}`, {
				method: "DELETE",
			});

			setIsDeleteDialogOpen(false);
			// Refresh global context. The ContextProvider will auto-select
			// the next available project or drop to a null state.
			await refreshContext();
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to delete project");
			setIsDeleting(false);
		}
	};

	return (
		<div className="space-y-8 animate-in fade-in duration-500">
			{/* Form Group 1: Project Details */}
			<Card className="border-border/50 shadow-sm bg-card/50">
				<CardHeader>
					<CardTitle>Project Details</CardTitle>
					<CardDescription>
						Manage the fundamental metadata of your workspace.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-6">
					{/* Project ID (Read-only) */}
					<div className="space-y-2">
						<label className="text-sm font-medium text-foreground">
							Project ID
						</label>
						<div className="flex max-w-md items-center gap-2">
							<Input
								readOnly
								value={projectId || ""}
								className="font-mono text-muted-foreground bg-muted/30"
							/>
							<Button
								type="button"
								variant="outline"
								size="icon"
								onClick={handleCopyId}
								className="shrink-0"
							>
								{isCopied ? (
									<Check className="h-4 w-4 text-emerald-500" />
								) : (
									<Copy className="h-4 w-4 text-muted-foreground" />
								)}
							</Button>
						</div>
						<p className="text-[13px] text-muted-foreground">
							Used as the{" "}
							<code className="text-xs text-foreground bg-muted px-1 rounded">
								project_id
							</code>{" "}
							in your local{" "}
							<code className="text-xs text-foreground bg-muted px-1 rounded">
								.ambyte/config.yaml
							</code>{" "}
							file.
						</p>
					</div>

					{/* Project Name */}
					<div className="space-y-2">
						<label
							htmlFor="projectName"
							className="text-sm font-medium text-foreground"
						>
							Project Name
						</label>
						<Input
							id="projectName"
							value={projectName}
							onChange={(e) => setProjectName(e.target.value)}
							className="max-w-md"
							placeholder="e.g. Production Data Governance"
						/>
					</div>

					{error && (
						<div className="text-sm text-rose-500 font-medium">{error}</div>
					)}
				</CardContent>
				<CardFooter className="border-t border-border/50 bg-muted/20 px-6 py-4">
					<Button
						onClick={handleSaveName}
						disabled={!hasChanges || isSaving || !projectName.trim()}
						className="min-w-[100px]"
					>
						{isSaving ? (
							<Loader2 className="h-4 w-4 animate-spin" />
						) : (
							"Save Changes"
						)}
					</Button>
				</CardFooter>
			</Card>

			{/* Form Group 2: Danger Zone */}
			<Card className="border-rose-500/30 bg-rose-500/5 shadow-sm">
				<CardHeader>
					<CardTitle className="text-rose-500 flex items-center gap-2">
						<AlertTriangle className="h-5 w-5" />
						Danger Zone
					</CardTitle>
					<CardDescription className="text-rose-500/80">
						Destructive actions that cannot be reversed.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-lg border border-rose-500/20 bg-rose-500/10 p-4">
						<div className="space-y-0.5">
							<h4 className="text-sm font-semibold text-rose-500">
								Delete Project
							</h4>
							<p className="text-[13px] text-rose-500/80">
								Permanently remove this project and all associated policies,
								resources, and audit logs.
							</p>
						</div>
						<Button
							variant="destructive"
							onClick={() => {
								setDeleteConfirmation("");
								setError(null);
								setIsDeleteDialogOpen(true);
							}}
							className="shrink-0"
						>
							Delete Project
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* The Terrifying Deletion Dialog */}
			<Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
				<DialogContent className="sm:max-w-md border-rose-500/30 shadow-2xl shadow-rose-900/20">
					<DialogHeader>
						<DialogTitle className="text-rose-500 flex items-center gap-2">
							<AlertTriangle className="h-5 w-5" />
							Delete Project
						</DialogTitle>
						<DialogDescription className="pt-2 text-foreground/80 leading-relaxed">
							This action <strong>cannot be undone</strong>. This will
							permanently delete the
							<span className="font-semibold text-foreground mx-1">
								{activeProject.name}
							</span>
							workspace and completely wipe all associated policies, API keys,
							inventory definitions, and immutable audit logs.
						</DialogDescription>
					</DialogHeader>

					<div className="py-4 space-y-3">
						<label className="text-sm font-medium text-foreground">
							Please type <strong>{activeProject.name}</strong> to confirm.
						</label>
						<Input
							value={deleteConfirmation}
							onChange={(e) => setDeleteConfirmation(e.target.value)}
							className="border-rose-500/50 focus-visible:ring-rose-500"
							placeholder={activeProject.name}
							autoComplete="off"
						/>
					</div>

					<DialogFooter className="gap-2 sm:gap-0">
						<Button
							variant="ghost"
							onClick={() => setIsDeleteDialogOpen(false)}
							disabled={isDeleting}
						>
							Cancel
						</Button>
						<Button
							variant="destructive"
							onClick={handleDeleteProject}
							disabled={deleteConfirmation !== activeProject.name || isDeleting}
							className="min-w-[120px]"
						>
							{isDeleting ? (
								<Loader2 className="h-4 w-4 animate-spin" />
							) : (
								"I understand, delete"
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}
