from enum import StrEnum


class Scope(StrEnum):
	# Full administrative access (Machine & Human)
	ADMIN = 'admin'

	# SDK / Decision Engine
	CHECK_WRITE = 'check:write'  # Allowed to call POST /v1/check
	AUDIT_WRITE = 'audit:write'  # Allowed to emit audit logs

	# Policy Management (CI/CD pipelines)
	POLICY_READ = 'policy:read'
	POLICY_WRITE = 'policy:write'

	# Inventory (Connectors)
	RESOURCE_WRITE = 'resource:write'

	# Lineage (Data Pipelines)
	LINEAGE_WRITE = 'lineage:write'
