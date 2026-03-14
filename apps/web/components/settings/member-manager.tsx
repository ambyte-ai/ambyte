"use client";

import {
    AlertTriangle,
    Loader2,
    MoreHorizontal,
    Shield,
    ShieldAlert,
    Trash2,
    UserPlus,
    Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
import { useMembers } from "@/hooks/use-members";
import { cn } from "@/lib/utils";
import type { ProjectMember, ProjectRole } from "@/types/settings";

// =============================================================================
// UI Helpers
// =============================================================================

const ROLE_COLORS: Record<ProjectRole, string> = {
    owner: "bg-purple-500/10 text-purple-400 border-purple-500/20",
    admin: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    editor: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    viewer: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
};

const ROLE_LABELS: Record<ProjectRole, string> = {
    owner: "Owner",
    admin: "Admin",
    editor: "Editor",
    viewer: "Viewer",
};

function getInitials(name: string | null, email: string): string {
    if (name) {
        const parts = name.split(" ");
        if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
        return name.substring(0, 2).toUpperCase();
    }
    return email.substring(0, 2).toUpperCase();
}

// =============================================================================
// Main Component
// =============================================================================

export function MemberManager() {
    const { members, isLoading, updateRole, removeMember } = useMembers();

    // State
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);
    const [memberToRemove, setMemberToRemove] = useState<ProjectMember | null>(null);
    const [isRemoving, setIsRemoving] = useState(false);

    // Safety Check: Calculate how many owners exist
    const ownerCount = useMemo(
        () => members.filter((m) => m.role === "owner").length,
        [members]
    );

    // Handlers
    const handleRoleChange = async (userId: string, newRole: ProjectRole) => {
        try {
            await updateRole(userId, newRole);
            toast.success(`Role updated to ${ROLE_LABELS[newRole]}`);
        } catch (err) {
            toast.error(
                err instanceof Error ? err.message : "Failed to update role"
            );
        }
    };

    const handleRemoveMember = async () => {
        if (!memberToRemove) return;
        setIsRemoving(true);
        try {
            await removeMember(memberToRemove.user_id);
            toast.success(`${memberToRemove.email} removed from project`);
            setMemberToRemove(null);
        } catch (err) {
            toast.error(
                err instanceof Error ? err.message : "Failed to remove member"
            );
        } finally {
            setIsRemoving(false);
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Header Section */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h3 className="text-lg font-medium text-foreground">
                        Members & Roles
                    </h3>
                    <p className="text-sm text-muted-foreground">
                        Manage who has access to this project and what they can do.
                    </p>
                </div>
                <Button
                    onClick={() => setIsAddModalOpen(true)}
                    className="gap-2 shrink-0"
                >
                    <UserPlus className="h-4 w-4" />
                    Invite Member
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
                ) : members.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 text-center border-dashed border-2 border-border/50 m-6 rounded-xl bg-muted/5">
                        <div className="h-12 w-12 rounded-full bg-indigo-500/10 flex items-center justify-center mb-4">
                            <Users className="h-6 w-6 text-indigo-400" />
                        </div>
                        <h4 className="text-sm font-semibold text-foreground">
                            No Members Found
                        </h4>
                        <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                            Invite your team to start collaborating on data policies.
                        </p>
                    </div>
                ) : (
                    <Table>
                        <TableHeader className="bg-muted/20">
                            <TableRow className="hover:bg-transparent">
                                <TableHead>User</TableHead>
                                <TableHead className="w-[200px]">Role</TableHead>
                                <TableHead className="w-[150px]">Joined</TableHead>
                                <TableHead className="w-[50px]"></TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {members.map((member) => {
                                const isLastOwner = ownerCount <= 1 && member.role === "owner";

                                return (
                                    <TableRow key={member.id} className="hover:bg-muted/30">
                                        <TableCell>
                                            <div className="flex items-center gap-3">
                                                {/* Avatar */}
                                                <div className="h-9 w-9 shrink-0 rounded-full bg-gradient-to-br from-zinc-800 to-zinc-900 border border-zinc-700 flex items-center justify-center text-xs font-semibold text-zinc-300 shadow-sm">
                                                    {getInitials(member.full_name, member.email)}
                                                </div>
                                                <div className="flex flex-col min-w-0">
                                                    <span className="font-medium text-sm text-foreground truncate">
                                                        {member.full_name || member.email.split("@")[0]}
                                                    </span>
                                                    <span className="text-xs text-muted-foreground truncate">
                                                        {member.email}
                                                    </span>
                                                </div>
                                            </div>
                                        </TableCell>

                                        <TableCell>
                                            {/* Inline Role Editing */}
                                            <Select
                                                value={member.role}
                                                onValueChange={(val) =>
                                                    handleRoleChange(member.user_id, val as ProjectRole)
                                                }
                                                disabled={isLastOwner}
                                            >
                                                <SelectTrigger
                                                    className={cn(
                                                        "h-8 border-border/50 bg-background/50 w-[140px]",
                                                        // Add subtle color hints to the trigger itself
                                                        member.role === "owner" && "text-purple-400",
                                                        member.role === "admin" && "text-blue-400",
                                                        member.role === "editor" && "text-emerald-400"
                                                    )}
                                                >
                                                    <SelectValue>
                                                        <div className="flex items-center gap-2">
                                                            <Badge
                                                                variant="outline"
                                                                className={cn(
                                                                    "px-1.5 py-0 uppercase text-[10px] font-mono border-transparent",
                                                                    ROLE_COLORS[member.role]
                                                                )}
                                                            >
                                                                {ROLE_LABELS[member.role]}
                                                            </Badge>
                                                        </div>
                                                    </SelectValue>
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {(Object.keys(ROLE_LABELS) as ProjectRole[]).map(
                                                        (roleKey) => (
                                                            <SelectItem key={roleKey} value={roleKey}>
                                                                <div className="flex items-center gap-2">
                                                                    <div
                                                                        className={cn(
                                                                            "h-2 w-2 rounded-full",
                                                                            ROLE_COLORS[roleKey].split(" ")[0] // Grab just the bg color
                                                                        )}
                                                                    />
                                                                    {ROLE_LABELS[roleKey]}
                                                                </div>
                                                            </SelectItem>
                                                        )
                                                    )}
                                                </SelectContent>
                                            </Select>
                                        </TableCell>

                                        <TableCell className="text-xs text-muted-foreground">
                                            {new Date(member.joined_at).toLocaleDateString()}
                                        </TableCell>

                                        <TableCell>
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8"
                                                        disabled={isLastOwner}
                                                    >
                                                        <MoreHorizontal className="h-4 w-4" />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end">
                                                    {isLastOwner ? (
                                                        <div className="px-2 py-1.5 text-xs text-muted-foreground flex items-center gap-2">
                                                            <ShieldAlert className="h-4 w-4 text-amber-500" />
                                                            Cannot remove last owner
                                                        </div>
                                                    ) : (
                                                        <DropdownMenuItem
                                                            className="text-rose-500 focus:text-rose-600 focus:bg-rose-500/10 cursor-pointer"
                                                            onClick={() => setMemberToRemove(member)}
                                                        >
                                                            <Trash2 className="mr-2 h-4 w-4" />
                                                            Remove from Project
                                                        </DropdownMenuItem>
                                                    )}
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                )}
            </Card>

            {/* Add Member Modal */}
            <AddMemberModal
                isOpen={isAddModalOpen}
                onOpenChange={setIsAddModalOpen}
            />

            {/* Remove Member Confirmation */}
            <Dialog
                open={!!memberToRemove}
                onOpenChange={(open) => !open && setMemberToRemove(null)}
            >
                <DialogContent className="sm:max-w-md border-rose-500/30">
                    <DialogHeader>
                        <DialogTitle className="text-rose-500 flex items-center gap-2">
                            <AlertTriangle className="h-5 w-5" />
                            Remove Member
                        </DialogTitle>
                        <DialogDescription className="pt-2">
                            Are you sure you want to remove <strong>{memberToRemove?.email}</strong>{" "}
                            from this project? They will immediately lose access to all policies and resources.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="mt-4">
                        <Button
                            variant="ghost"
                            onClick={() => setMemberToRemove(null)}
                            disabled={isRemoving}
                        >
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={handleRemoveMember}
                            disabled={isRemoving}
                        >
                            {isRemoving ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                "Remove Member"
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

// =============================================================================
// Add Member Modal
// =============================================================================

function AddMemberModal({
    isOpen,
    onOpenChange,
}: {
    isOpen: boolean;
    onOpenChange: (open: boolean) => void;
}) {
    const { addMember } = useMembers();

    // Form State
    const [email, setEmail] = useState("");
    const [role, setRole] = useState<ProjectRole>("viewer");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleOpenChange = (open: boolean) => {
        if (!open) {
            setTimeout(() => {
                setEmail("");
                setRole("viewer");
                setError(null);
            }, 300);
        }
        onOpenChange(open);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!email.trim()) {
            setError("Email address is required.");
            return;
        }

        setIsSubmitting(true);
        setError(null);

        try {
            // Backend expects the user to already exist in the Clerk Org
            await addMember({ email: email.trim(), role });
            toast.success(`${email} added to project as ${ROLE_LABELS[role]}`);
            handleOpenChange(false);
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : "User not found or already in project."
            );
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={handleOpenChange}>
            <DialogContent className="sm:max-w-md border-border/50">
                <form onSubmit={handleSubmit}>
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Shield className="h-5 w-5 text-indigo-400" />
                            Invite Member
                        </DialogTitle>
                        <DialogDescription>
                            Add an existing organization member to this project.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="py-6 space-y-6">
                        <div className="space-y-3">
                            <Label htmlFor="userEmail">Email Address</Label>
                            <Input
                                id="userEmail"
                                type="email"
                                placeholder="colleague@yourcompany.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                autoFocus
                                className="bg-background"
                            />
                            <p className="text-[11px] text-muted-foreground">
                                User must have logged into the Ambyte platform at least once to
                                be provisioned.
                            </p>
                        </div>

                        <div className="space-y-3">
                            <Label>Project Role</Label>
                            <Select
                                value={role}
                                onValueChange={(v) => setRole(v as ProjectRole)}
                            >
                                <SelectTrigger className="bg-background">
                                    <SelectValue placeholder="Select a role" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="owner">
                                        <div className="flex flex-col gap-1 py-1">
                                            <span className="font-medium text-purple-400">Owner</span>
                                            <span className="text-[10px] text-muted-foreground">
                                                Full access including deleting the project.
                                            </span>
                                        </div>
                                    </SelectItem>
                                    <SelectItem value="admin">
                                        <div className="flex flex-col gap-1 py-1">
                                            <span className="font-medium text-blue-400">Admin</span>
                                            <span className="text-[10px] text-muted-foreground">
                                                Can manage members, API keys, and all policies.
                                            </span>
                                        </div>
                                    </SelectItem>
                                    <SelectItem value="editor">
                                        <div className="flex flex-col gap-1 py-1">
                                            <span className="font-medium text-emerald-400">
                                                Editor
                                            </span>
                                            <span className="text-[10px] text-muted-foreground">
                                                Can create and edit policies and inventory.
                                            </span>
                                        </div>
                                    </SelectItem>
                                    <SelectItem value="viewer">
                                        <div className="flex flex-col gap-1 py-1">
                                            <span className="font-medium text-zinc-400">Viewer</span>
                                            <span className="text-[10px] text-muted-foreground">
                                                Read-only access to policies and dashboards.
                                            </span>
                                        </div>
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        {error && (
                            <div className="text-sm font-medium text-rose-500 bg-rose-500/10 p-3 rounded-md border border-rose-500/20 flex items-start gap-2">
                                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                                <span>{error}</span>
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
                        <Button type="submit" disabled={isSubmitting || !email.trim()}>
                            {isSubmitting ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Adding...
                                </>
                            ) : (
                                "Add Member"
                            )}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}