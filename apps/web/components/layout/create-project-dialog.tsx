"use client";

import { FolderKanban, Loader2, Sparkles } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useProject } from "@/context/project-context";
import { useAmbyteApi } from "@/hooks/use-ambyte-api";

interface CreateProjectDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function CreateProjectDialog({
	open,
	onOpenChange,
}: CreateProjectDialogProps) {
	const api = useAmbyteApi();
	const { refreshContext, setProjectId } = useProject();

	const [name, setName] = useState("");
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const inputRef = useRef<HTMLInputElement>(null);

	const resetForm = useCallback(() => {
		setName("");
		setError(null);
		setIsSubmitting(false);
	}, []);

	const handleOpenChange = useCallback(
		(nextOpen: boolean) => {
			if (!nextOpen) {
				resetForm();
			}
			onOpenChange(nextOpen);
		},
		[onOpenChange, resetForm],
	);

	const handleSubmit = useCallback(
		async (e: React.FormEvent) => {
			e.preventDefault();

			const trimmedName = name.trim();
			if (!trimmedName) {
				setError("Project name is required");
				inputRef.current?.focus();
				return;
			}

			if (trimmedName.length < 2) {
				setError("Project name must be at least 2 characters");
				inputRef.current?.focus();
				return;
			}

			if (trimmedName.length > 64) {
				setError("Project name must be 64 characters or fewer");
				inputRef.current?.focus();
				return;
			}

			setIsSubmitting(true);
			setError(null);

			try {
				const created = await api("/projects/", {
					method: "POST",
					body: JSON.stringify({ name: trimmedName }),
				});

				// Refresh the project list in context
				await refreshContext();

				// Auto-select the newly created project
				if (created?.id) {
					setProjectId(created.id);
				}

				toast.success("Project created", {
					description: `"${trimmedName}" is ready to go.`,
				});

				handleOpenChange(false);
			} catch (err) {
				const message =
					err instanceof Error
						? err.message
						: "Something went wrong. Please try again.";
				setError(message);
			} finally {
				setIsSubmitting(false);
			}
		},
		[name, api, refreshContext, setProjectId, handleOpenChange],
	);

	return (
		<Dialog open={open} onOpenChange={handleOpenChange}>
			<DialogContent className="sm:max-w-[480px] p-0 gap-0 overflow-hidden">
				{/* Gradient decorative header */}
				<div className="relative px-6 pt-8 pb-6 bg-gradient-to-br from-indigo-500/10 via-violet-500/10 to-fuchsia-500/10">
					<div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent" />
					<div className="relative flex items-center gap-3">
						<div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/25">
							<FolderKanban className="h-5 w-5" />
						</div>
						<DialogHeader className="flex-1 space-y-1">
							<DialogTitle className="text-xl font-semibold tracking-tight">
								Create Project
							</DialogTitle>
							<DialogDescription className="text-sm text-muted-foreground">
								Projects organize your data sources, policies, and
								audit trails.
							</DialogDescription>
						</DialogHeader>
					</div>
				</div>

				{/* Form body */}
				<form onSubmit={handleSubmit} id="create-project-form">
					<div className="px-6 py-6 space-y-4">
						<div className="space-y-2">
							<Label
								htmlFor="project-name"
								className="text-sm font-medium"
							>
								Project Name
							</Label>
							<Input
								ref={inputRef}
								id="project-name"
								placeholder="e.g. Customer Data Platform"
								value={name}
								onChange={(e) => {
									setName(e.target.value);
									if (error) setError(null);
								}}
								disabled={isSubmitting}
								autoFocus
								autoComplete="off"
								className={
									error
										? "border-destructive focus-visible:ring-destructive/40"
										: ""
								}
							/>
							{error && (
								<p className="text-xs text-destructive flex items-center gap-1 animate-in fade-in-0 slide-in-from-top-1 duration-200">
									{error}
								</p>
							)}
							<p className="text-xs text-muted-foreground">
								You can rename this later from project settings.
							</p>
						</div>
					</div>

					{/* Footer */}
					<DialogFooter className="px-6 py-4 bg-muted/30 border-t border-border">
						<Button
							type="button"
							variant="ghost"
							onClick={() => handleOpenChange(false)}
							disabled={isSubmitting}
						>
							Cancel
						</Button>
						<Button
							type="submit"
							variant="gradient"
							disabled={isSubmitting || !name.trim()}
							className="min-w-[140px]"
						>
							{isSubmitting ? (
								<>
									<Loader2 className="h-4 w-4 animate-spin" />
									Creating…
								</>
							) : (
								<>
									<Sparkles className="h-4 w-4" />
									Create Project
								</>
							)}
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}
