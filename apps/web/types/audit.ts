// =============================================================================
// Enums & Basic Types
// =============================================================================

export type Decision = "ALLOW" | "DENY" | "DRY_RUN_DENY" | "UNSPECIFIED";

export enum ActorType {
    ACTOR_TYPE_UNSPECIFIED = 0,
    ACTOR_TYPE_HUMAN = 1,
    ACTOR_TYPE_SERVICE_ACCOUNT = 2,
    ACTOR_TYPE_SYSTEM_INTERNAL = 3,
}

export interface Actor {
    id: string;
    type: ActorType | number;
    roles: string[];
    attributes: Record<string, string>;
}

// =============================================================================
// List View Models (GET /v1/audit/)
// Maps to backend: src/schemas/audit.py -> AuditLogRead
// =============================================================================

export interface PolicyContribution {
    obligation_id: string;
    source_id: string;
    effect: string;
    reason: string;
}

export interface ReasonTrace {
    decision_reason: string;
    cache_hit: boolean;
    resolved_policy_hash: string | null;
    contributing_policies: PolicyContribution[];
    lineage_constraints: string[]; // Upstream poison pills
}

/**
 * Represents a single row in the Audit Ledger table.
 */
export interface AuditLog {
    id: string;
    project_id: string;
    timestamp: string; // ISO 8601 DateTime
    actor_id: string;
    resource_urn: string;
    action: string;
    decision: Decision;
    reason_trace: ReasonTrace | null;
    request_context: Record<string, any> | null;
    entry_hash: string;
    block_id: string | null; // If null, the log is currently buffered/unsealed
}

// =============================================================================
// Cryptographic Proof Models (GET /v1/audit/proof/{id})
// Maps to backend: ambyte_schemas/models/audit.py -> AuditProof
// =============================================================================

export interface PolicyEvaluationTrace {
    reason_summary: string;
    contributing_obligation_ids: string[];
    policy_version_hash: string;
    cache_hit: boolean;
}

/**
 * The canonical log entry used for Merkle Tree hashing.
 * Notice it uses the full `Actor` object instead of just `actor_id`.
 */
export interface AuditLogEntry {
    id: string;
    timestamp: string; // ISO 8601 DateTime
    actor: Actor;
    resource_urn: string;
    action: string;
    decision: Decision;
    evaluation_trace: PolicyEvaluationTrace | null;
    request_context: Record<string, any>;
    entry_hash: string;
}

/**
 * The signed block header that cryptographically seals a time-window of logs.
 */
export interface AuditBlockHeader {
    id: string;
    sequence_index: number;
    prev_block_hash: string;
    merkle_root: string;
    timestamp_start: string; // ISO 8601 DateTime
    timestamp_end: string; // ISO 8601 DateTime
    log_count: number;
    signature: string; // Hex string (Ed25519 Signature)
}

/**
 * The complete verification bundle returned by the API.
 */
export interface AuditProof {
    entry: AuditLogEntry;
    block_header: AuditBlockHeader;
    merkle_siblings: string[]; // Hashes needed to rebuild the path to the root
}