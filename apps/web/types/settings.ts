// =============================================================================
// RBAC / Team Memberships
// =============================================================================

export type ProjectRole = "owner" | "admin" | "editor" | "viewer";

export interface ProjectMember {
	id: string;
	user_id: string;
	email: string;
	full_name: string | null;
	role: ProjectRole;
	joined_at: string; // ISO 8601 Date string
}

// Payload for POST /v1/projects/{project_id}/members
export interface AddMemberPayload {
	email: string;
	role: ProjectRole;
}

// =============================================================================
// API Keys (Machine Credentials)
// =============================================================================

export interface ApiKey {
	id: string;
	name: string;
	prefix: string; // e.g., "sk_live_a1b2..."
	scopes: string[];
	created_at: string; // ISO 8601 Date string
	last_used_at: string | null; // ISO 8601 Date string
	expires_at: string | null; // ISO 8601 Date string
}

// Returned only once immediately after creation
export interface ApiKeySecret {
	key: string; // The raw unhashed token (e.g. sk_live_xyz123)
	info: ApiKey;
}

// Payload for POST /v1/projects/{project_id}/keys
export interface CreateApiKeyPayload {
	name: string;
	scopes: string[];
	expires_at?: string | null; // ISO 8601 Date string or null
}

// =============================================================================
// Audit & Security
// =============================================================================

export interface PublicKeyResponse {
	public_key: string;
}

// =============================================================================
// Project General
// =============================================================================

export interface ProjectUpdatePayload {
	name: string;
}
