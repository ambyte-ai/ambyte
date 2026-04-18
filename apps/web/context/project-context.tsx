"use client";

import { useAuth, useOrganization } from "@clerk/nextjs";
import type React from "react";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useAmbyteApi } from "@/hooks/use-ambyte-api";

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

interface Project {
	id: string;
	name: string;
	role: string | null;
}

interface Organization {
	id: string;
	name: string;
	isPersonal: boolean;
}

interface ProjectContextType {
	// Current Selection
	projectId: string | null;
	organizationId: string | null;

	// Metadata
	projects: Project[];
	organization: Organization | null;
	isLoading: boolean;
	error: Error | null;

	// Actions
	setProjectId: (id: string) => void;
	refreshContext: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

// -----------------------------------------------------------------------------
// Provider
// -----------------------------------------------------------------------------

export function ProjectProvider({ children }: { children: React.ReactNode }) {
	const api = useAmbyteApi();
	const { organization: clerkOrg } = useOrganization();
	const { isLoaded, isSignedIn } = useAuth();

	// State
	const [projectId, setProjectId] = useState<string | null>(null);
	const [organizationId, setOrganizationId] = useState<string | null>(null);
	const [projects, setProjects] = useState<Project[]>([]);
	const [organization, setOrganization] = useState<Organization | null>(null);

	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<Error | null>(null);

	// Track Clerk's org ID to detect when user switches organizations
	// Note: For personal orgs, clerkOrg is null - the API is the source of truth
	const prevClerkOrgIdRef = useRef<string | null | undefined>(undefined);

	// Listen for Clerk org changes (handles team org switching)
	// Personal org users will have clerkOrg = null, and the API response is authoritative
	useEffect(() => {
		const currentClerkOrgId = clerkOrg?.id ?? null;

		// Skip the first render (when ref is undefined)
		if (prevClerkOrgIdRef.current === undefined) {
			prevClerkOrgIdRef.current = currentClerkOrgId;
			return;
		}

		// If Clerk org has changed (including switching to/from personal org), refresh
		if (prevClerkOrgIdRef.current !== currentClerkOrgId) {
			prevClerkOrgIdRef.current = currentClerkOrgId;

			// 1. Clear projects immediately to prevent data leakage
			setProjects([]);

			// 2. Reset project selection
			setProjectId(null);

			// 3. Clear current org while loading new one
			setOrganization(null);

			// 4. Fetch new org's data from API (source of truth)
			refreshContext();
		}
	}, [clerkOrg?.id]);

	// Helper to get org-scoped localStorage key
	const getStorageKey = (orgId: string) => `ambyte_project_${orgId}`;

	// Initial Load & Refresh Logic
	const refreshContext = async () => {
		setIsLoading(true);
		setError(null);
		try {
			// Call the /whoami endpoint to get the user's hierarchy
			// This endpoint is implemented in apps/control_plane_api/src/api/v1/endpoints/auth.py
			const data = await api("/auth/whoami");

			// 1. Set Org Info
			const currentOrgId = data.organization_id;
			setOrganizationId(currentOrgId);
			setOrganization({
				id: currentOrgId,
				name: data.organization_name,
				isPersonal: data.is_personal ?? false,
			});

			// 2. Set Projects List
			setProjects(data.projects || []);

			// 3. Determine Active Project
			// Priority: LocalStorage (org-scoped) -> First Available -> None
			const storageKey = getStorageKey(currentOrgId);
			const savedId = localStorage.getItem(storageKey);
			const isValidSaved = data.projects.find((p: Project) => p.id === savedId);

			if (isValidSaved) {
				setProjectId(savedId);
			} else if (data.projects.length > 0) {
				const defaultId = data.projects[0].id;
				setProjectId(defaultId);
				localStorage.setItem(storageKey, defaultId);
			} else {
				setProjectId(null);
			}
		} catch (err) {
			console.error("Failed to load project context:", err);
			setError(
				err instanceof Error ? err : new Error("Failed to load context"),
			);
		} finally {
			setIsLoading(false);
		}
	};

	// Trigger load on mount
	useEffect(() => {
		if (isLoaded && isSignedIn) {
			refreshContext();
		}
	}, [api, isLoaded, isSignedIn]);

	// Handle manual project switching
	const handleSetProject = (id: string) => {
		// Validate it exists in our list
		if (projects.find((p) => p.id === id) && organizationId) {
			setProjectId(id);
			localStorage.setItem(getStorageKey(organizationId), id);
		}
	};

	return (
		<ProjectContext.Provider
			value={{
				projectId,
				organizationId,
				projects,
				organization,
				isLoading,
				error,
				setProjectId: handleSetProject,
				refreshContext,
			}}
		>
			{children}
		</ProjectContext.Provider>
	);
}

// -----------------------------------------------------------------------------
// Hook
// -----------------------------------------------------------------------------

export function useProject() {
	const context = useContext(ProjectContext);
	if (context === undefined) {
		throw new Error("useProject must be used within a ProjectProvider");
	}
	return context;
}
