// =============================================================================
// Enums
// These map to the Integer values returned by the API (Protobuf mappings)
// =============================================================================

export enum EnforcementLevel {
	UNSPECIFIED = 0,
	BLOCKING = 1,
	AUDIT_ONLY = 2,
	NOTIFY_HUMAN = 3,
}

export enum RetentionTrigger {
	UNSPECIFIED = 0,
	CREATION_DATE = 1,
	LAST_ACCESS_DATE = 2,
	EVENT_DATE = 3,
	DATA_SUBJECT_REQUEST = 4,
}

export enum PrivacyMethod {
	UNSPECIFIED = 0,
	PSEUDONYMIZATION = 1,
	ANONYMIZATION = 2,
	DIFFERENTIAL_PRIVACY = 3,
	ROW_LEVEL_SECURITY = 4,
}

// =============================================================================
// Metadata & Scoping
// =============================================================================

export interface SourceProvenance {
	source_id: string; // e.g., "GDPR-Art-17"
	document_type: string; // e.g., "REGULATION", "CONTRACT"
	section_reference?: string; // e.g., "Section 4.1"
	document_uri?: string; // S3 URL or external link
}

export interface ResourceSelector {
	include_patterns: string[]; // e.g. ["urn:snowflake:sales:*"]
	exclude_patterns: string[]; // e.g. ["urn:snowflake:sales:tmp_*"]
	match_tags: Record<string, string>; // e.g. { "sensitivity": "high" }
}

// =============================================================================
// Constraint Definitions (Polymorphic Logic)
// =============================================================================

export interface RetentionRule {
	duration: string; // ISO 8601 Duration string (e.g. "P30D", "P1Y")
	trigger: RetentionTrigger;
	allow_legal_hold_override: boolean;
}

export interface GeofencingRule {
	allowed_regions: string[]; // ISO 3166-1 alpha-2 codes (e.g., "US", "DE")
	denied_regions: string[];
	strict_residency: boolean;
}

export interface PurposeRestriction {
	allowed_purposes: string[]; // e.g. ["ANALYTICS", "MARKETING"]
	denied_purposes: string[];
}

export interface PrivacyEnhancementRule {
	method: PrivacyMethod;
	parameters: Record<string, string>; // e.g. { "epsilon": "0.5", "k": "10" }
}

export interface AiModelConstraint {
	training_allowed: boolean;
	fine_tuning_allowed: boolean;
	rag_usage_allowed: boolean;
	requires_open_source_release: boolean;
	attribution_text_required?: string;
}

// =============================================================================
// The Root Object
// =============================================================================

export interface Obligation {
	id: string; // Slug, e.g. "gdpr-retention-customer"
	title: string;
	description: string;
	is_active: boolean;

	// Metadata
	provenance: SourceProvenance;
	enforcement_level: EnforcementLevel;
	target: ResourceSelector;

	// Polymorphic Constraints (Only one should be populated per object)
	retention?: RetentionRule | null;
	geofencing?: GeofencingRule | null;
	purpose?: PurposeRestriction | null;
	privacy?: PrivacyEnhancementRule | null;
	ai_model?: AiModelConstraint | null;

	// System
	created_at?: string; // ISO 8601 DateTime
	updated_at?: string; // ISO 8601 DateTime
}

// Helper Type for UI Filters
export type ConstraintType =
	| "retention"
	| "geofencing"
	| "purpose"
	| "privacy"
	| "ai_model";

// =============================================================================
// Mapping Utilities (Optional, for UI labels)
// =============================================================================

export const ENFORCEMENT_LABELS: Record<EnforcementLevel, string> = {
	[EnforcementLevel.UNSPECIFIED]: "Unspecified",
	[EnforcementLevel.BLOCKING]: "Blocking",
	[EnforcementLevel.AUDIT_ONLY]: "Audit Only",
	[EnforcementLevel.NOTIFY_HUMAN]: "Notify Human",
};

export const PRIVACY_METHOD_LABELS: Record<PrivacyMethod, string> = {
	[PrivacyMethod.UNSPECIFIED]: "Unspecified",
	[PrivacyMethod.PSEUDONYMIZATION]: "Pseudonymization",
	[PrivacyMethod.ANONYMIZATION]: "Anonymization",
	[PrivacyMethod.DIFFERENTIAL_PRIVACY]: "Differential Privacy",
	[PrivacyMethod.ROW_LEVEL_SECURITY]: "Row Level Security",
};
