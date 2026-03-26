"use client";

import {
	AlertTriangle,
	Check,
	Clock,
	Copy,
	Key,
	Loader2,
	MoreHorizontal,
	Plus,
	TerminalSquare,
	Trash2,
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { useApiKeys } from "@/hooks/use-api-keys";
import type { ApiKey, ApiKeySecret } from "@/types/settings";

const AVAILABLE_SCOPES = [
	{ id: "check:write", label: "Decision Engine (check:write)" },
	{ id: "audit:write", label: "Audit Logging (audit:write)" },
	{ id: "policy:write", label: "Policy Management (policy:write)" },
	{ id: "policy:read", label: "Read Policies (policy:read)" },
	{ id: "resource:write", label: "Inventory Sync (resource:write)" },
	{ id: "lineage:write", label: "Lineage Tracking (lineage:write)" },
];

export function ApiKeyManager() {
	const { keys, isLoading, revokeKey } = useApiKeys();
	const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
	const [keyToRevoke, setKeyToRevoke] = useState<ApiKey | null>(null);

	return (
		<div className="space-y-6 animate-in fade-in duration-500">
			{/* Header Section */}
			<div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
				<div>
					<h3 className="text-lg font-medium text-foreground">API Keys</h3>
					<p className="text-sm text-muted-foreground">
						Generate and manage machine credentials for the Ambyte SDK, CLI, and
						data connectors.
					</p>
				</div>
				<Button
					onClick={() => setIsCreateModalOpen(true)}
					className="gap-2 shrink-0"
				>
					<Plus className="h-4 w-4" />
					Create New Key
				</Button>
			</div>

			{/* Main Content Area */}
			<Card className="border-border/50 shadow-sm bg-card">
				{isLoading ? (
					<div className="p-6 space-y-4">
						<Skeleton className="h-10 w-full bg-muted/50" />
						<Skeleton className="h-10 w-full bg-muted/50" />
						<Skeleton className="h-10 w-full bg-muted/50" />
					</div>
				) : keys.length === 0 ? (
					<div className="flex flex-col items-center justify-center py-16 text-center border-dashed border-2 border-border/50 m-6 rounded-xl bg-muted/5">
						<div className="h-12 w-12 rounded-full bg-indigo-500/10 flex items-center justify-center mb-4">
							<Key className="h-6 w-6 text-indigo-400" />
						</div>
						<h4 className="text-sm font-semibold text-foreground">
							No API Keys Found
						</h4>
						<p className="text-sm text-muted-foreground mt-1 max-w-sm">
							You haven't generated any machine credentials yet. Create one to
							connect your pipelines.
						</p>
						<Button
							variant="outline"
							className="mt-6"
							onClick={() => setIsCreateModalOpen(true)}
						>
							Generate First Key
						</Button>
					</div>
				) : (
					<Table>
						<TableHeader className="bg-muted/20">
							<TableRow className="hover:bg-transparent">
								<TableHead className="w-[200px]">Name</TableHead>
								<TableHead>Prefix</TableHead>
								<TableHead className="w-[250px]">Scopes</TableHead>
								<TableHead>Created</TableHead>
								<TableHead>Last Used</TableHead>
								<TableHead className="w-[50px]"></TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{keys.map((apiKey) => (
								<TableRow key={apiKey.id} className="hover:bg-muted/30">
									<TableCell className="font-medium text-foreground">
										{apiKey.name}
									</TableCell>
									<TableCell>
										<code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono text-muted-foreground">
											{apiKey.prefix}••••••••
										</code>
									</TableCell>
									<TableCell>
										<div className="flex flex-wrap gap-1">
											{apiKey.scopes.slice(0, 2).map((scope) => (
												<Badge
													key={scope}
													variant="secondary"
													className="text-[10px] font-mono px-1.5 py-0"
												>
													{scope}
												</Badge>
											))}
											{apiKey.scopes.length > 2 && (
												<Badge
													variant="outline"
													className="text-[10px] px-1.5 py-0"
												>
													+{apiKey.scopes.length - 2}
												</Badge>
											)}
										</div>
									</TableCell>
									<TableCell className="text-xs text-muted-foreground">
										{new Date(apiKey.created_at).toLocaleDateString()}
									</TableCell>
									<TableCell className="text-xs text-muted-foreground">
										{apiKey.last_used_at ? (
											<span className="flex items-center gap-1.5">
												<Clock className="h-3 w-3" />
												{new Date(apiKey.last_used_at).toLocaleDateString()}
											</span>
										) : (
											<span className="opacity-50">Never</span>
										)}
									</TableCell>
									<TableCell>
										<DropdownMenu>
											<DropdownMenuTrigger asChild>
												<Button variant="ghost" size="icon" className="h-8 w-8">
													<MoreHorizontal className="h-4 w-4" />
												</Button>
											</DropdownMenuTrigger>
											<DropdownMenuContent align="end">
												<DropdownMenuItem
													className="text-rose-500 focus:text-rose-600 focus:bg-rose-500/10 cursor-pointer"
													onClick={() => setKeyToRevoke(apiKey)}
												>
													<Trash2 className="mr-2 h-4 w-4" />
													Revoke Key
												</DropdownMenuItem>
											</DropdownMenuContent>
										</DropdownMenu>
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				)}
			</Card>

			{/* Create Key Modal */}
			<CreateKeyModal
				isOpen={isCreateModalOpen}
				onOpenChange={setIsCreateModalOpen}
			/>

			{/* Revoke Key Confirmation Modal */}
			<Dialog
				open={!!keyToRevoke}
				onOpenChange={(open) => !open && setKeyToRevoke(null)}
			>
				<DialogContent className="sm:max-w-md border-rose-500/30">
					<DialogHeader>
						<DialogTitle className="text-rose-500 flex items-center gap-2">
							<AlertTriangle className="h-5 w-5" />
							Revoke API Key
						</DialogTitle>
						<DialogDescription className="pt-2">
							Are you sure you want to revoke the key{" "}
							<strong>{keyToRevoke?.name}</strong>? Any applications or
							pipelines using this key will immediately lose access. This action
							cannot be undone.
						</DialogDescription>
					</DialogHeader>
					<DialogFooter className="mt-4">
						<Button variant="ghost" onClick={() => setKeyToRevoke(null)}>
							Cancel
						</Button>
						<Button
							variant="destructive"
							onClick={async () => {
								if (keyToRevoke) {
									await revokeKey(keyToRevoke.id);
									setKeyToRevoke(null);
								}
							}}
						>
							Revoke Key
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}

// =============================================================================
// Create Key Modal (Handles both Form & Result States)
// =============================================================================

function CreateKeyModal({
	isOpen,
	onOpenChange,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
}) {
	const { createKey } = useApiKeys();

	// Form State
	const [name, setName] = useState("");
	const [scopes, setScopes] = useState<string[]>([
		"check:write",
		"audit:write",
	]);
	const [expirationDays, setExpirationDays] = useState<string>("90");

	// Submission State
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// Result State
	const [generatedSecret, setGeneratedSecret] = useState<ApiKeySecret | null>(
		null,
	);
	const [isCopied, setIsCopied] = useState(false);

	// Reset state when modal closes
	const handleOpenChange = (open: boolean) => {
		if (!open) {
			setTimeout(() => {
				setName("");
				setScopes(["check:write", "audit:write"]);
				setExpirationDays("90");
				setGeneratedSecret(null);
				setError(null);
			}, 300); // Wait for exit animation
		}
		onOpenChange(open);
	};

	const toggleScope = (scopeId: string) => {
		setScopes((current) =>
			current.includes(scopeId)
				? current.filter((s) => s !== scopeId)
				: [...current, scopeId],
		);
	};

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!name.trim()) {
			setError("Name is required.");
			return;
		}
		if (scopes.length === 0) {
			setError("Select at least one scope.");
			return;
		}

		setIsSubmitting(true);
		setError(null);

		try {
			// Calculate expiration date
			let expiresAt: string | null = null;
			if (expirationDays !== "never") {
				const date = new Date();
				date.setDate(date.getDate() + parseInt(expirationDays));
				expiresAt = date.toISOString();
			}

			const secret = await createKey({
				name: name.trim(),
				scopes,
				expires_at: expiresAt,
			});

			setGeneratedSecret(secret);
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to create key.");
		} finally {
			setIsSubmitting(false);
		}
	};

	const copyToClipboard = async () => {
		if (generatedSecret) {
			await navigator.clipboard.writeText(generatedSecret.key);
			setIsCopied(true);
			setTimeout(() => setIsCopied(false), 2000);
		}
	};

	return (
		<Dialog open={isOpen} onOpenChange={handleOpenChange}>
			<DialogContent className="sm:max-w-[500px] border-border/50">
				{!generatedSecret ? (
					// -------------------------------------------------------------------
					// STEP 1: FORM
					// -------------------------------------------------------------------
					<form onSubmit={handleSubmit}>
						<DialogHeader>
							<DialogTitle className="flex items-center gap-2">
								<TerminalSquare className="h-5 w-5 text-indigo-400" />
								Create API Key
							</DialogTitle>
							<DialogDescription>
								Create a machine credential scoped to specific operations.
							</DialogDescription>
						</DialogHeader>

						<div className="py-6 space-y-6">
							<div className="space-y-3">
								<Label htmlFor="keyName">Key Name</Label>
								<Input
									id="keyName"
									placeholder="e.g., Airflow Prod Worker"
									value={name}
									onChange={(e) => setName(e.target.value)}
									autoFocus
									className="bg-background"
								/>
							</div>

							<div className="space-y-3">
								<Label>Expiration</Label>
								<Select
									value={expirationDays}
									onValueChange={setExpirationDays}
								>
									<SelectTrigger className="bg-background">
										<SelectValue placeholder="Select expiration" />
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="30">30 Days</SelectItem>
										<SelectItem value="90">90 Days</SelectItem>
										<SelectItem value="365">1 Year</SelectItem>
										<SelectItem value="never">
											Never (Not Recommended)
										</SelectItem>
									</SelectContent>
								</Select>
							</div>

							<div className="space-y-3">
								<Label>Permissions (Scopes)</Label>
								<div className="grid gap-3 p-4 border rounded-lg bg-muted/10">
									{AVAILABLE_SCOPES.map((scope) => (
										<div key={scope.id} className="flex items-center space-x-3">
											<Checkbox
												id={scope.id}
												checked={scopes.includes(scope.id)}
												onCheckedChange={() => toggleScope(scope.id)}
											/>
											<Label
												htmlFor={scope.id}
												className="text-sm font-normal cursor-pointer leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
											>
												{scope.label}
											</Label>
										</div>
									))}
								</div>
							</div>

							{error && (
								<div className="text-sm font-medium text-rose-500 bg-rose-500/10 p-3 rounded-md border border-rose-500/20">
									{error}
								</div>
							)}
						</div>

						<DialogFooter>
							<Button
								type="button"
								variant="ghost"
								onClick={() => handleOpenChange(false)}
								disabled={isSubmitting}
							>
								Cancel
							</Button>
							<Button type="submit" disabled={isSubmitting || !name.trim()}>
								{isSubmitting ? (
									<>
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
										Generating...
									</>
								) : (
									"Generate Key"
								)}
							</Button>
						</DialogFooter>
					</form>
				) : (
					// -------------------------------------------------------------------
					// STEP 2: RESULT
					// -------------------------------------------------------------------
					<div className="space-y-6">
						<DialogHeader>
							<DialogTitle className="flex items-center gap-2 text-emerald-500">
								<Check className="h-6 w-6" />
								API Key Generated
							</DialogTitle>
							<DialogDescription className="text-foreground/90">
								Please copy this key and store it securely. For your protection,
								<strong> you will not be able to see it again</strong> after
								closing this window.
							</DialogDescription>
						</DialogHeader>

						<div className="p-1 rounded-lg bg-gradient-to-br from-indigo-500 via-purple-500 to-emerald-500">
							<div className="flex items-center justify-between p-4 bg-zinc-950 rounded-md">
								<code className="text-emerald-400 font-mono text-sm break-all pr-4">
									{generatedSecret.key}
								</code>
								<Button
									variant="secondary"
									size="icon"
									className="shrink-0 h-8 w-8 hover:bg-emerald-500/20 hover:text-emerald-400"
									onClick={copyToClipboard}
								>
									{isCopied ? (
										<Check className="h-4 w-4" />
									) : (
										<Copy className="h-4 w-4" />
									)}
								</Button>
							</div>
						</div>

						<DialogFooter className="sm:justify-center pt-2">
							<Button
								variant="outline"
								onClick={() => handleOpenChange(false)}
								className="w-full"
							>
								I have saved my key securely
							</Button>
						</DialogFooter>
					</div>
				)}
			</DialogContent>
		</Dialog>
	);
}
