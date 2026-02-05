"use client";

import type React from "react";
import { createContext, useContext, useEffect, useState } from "react";
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

	// State
	const [projectId, setProjectId] = useState<string | null>(null);
	const [organizationId, setOrganizationId] = useState<string | null>(null);
	const [projects, setProjects] = useState<Project[]>([]);
	const [organization, setOrganization] = useState<Organization | null>(null);

	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<Error | null>(null);

	// Initial Load & Refresh Logic
	const refreshContext = async () => {
		setIsLoading(true);
		setError(null);
		try {
			// Call the /whoami endpoint to get the user's hierarchy
			// This endpoint is implemented in apps/control_plane_api/src/api/v1/endpoints/auth.py
			const data = await api("/auth/whoami");

			// 1. Set Org Info
			setOrganizationId(data.organization_id);
			setOrganization({
				id: data.organization_id,
				name: data.organization_name,
			});

			// 2. Set Projects List
			setProjects(data.projects || []);

			// 3. Determine Active Project
			// Priority: LocalStorage -> First Available -> None
			const savedId = localStorage.getItem("ambyte_project_id");
			const isValidSaved = data.projects.find((p: Project) => p.id === savedId);

			if (isValidSaved) {
				setProjectId(savedId);
			} else if (data.projects.length > 0) {
				const defaultId = data.projects[0].id;
				setProjectId(defaultId);
				localStorage.setItem("ambyte_project_id", defaultId);
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
		refreshContext();
	}, [api]);

	// Handle manual project switching
	const handleSetProject = (id: string) => {
		// Validate it exists in our list
		if (projects.find((p) => p.id === id)) {
			setProjectId(id);
			localStorage.setItem("ambyte_project_id", id);
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
