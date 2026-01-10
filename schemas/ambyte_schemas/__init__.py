import os
import sys

_proto_dir = os.path.join(os.path.dirname(__file__), 'proto')
if _proto_dir not in sys.path:
	sys.path.append(_proto_dir)

from ambyte_schemas.models.audit import (  # noqa: E402
	AuditBlockHeader,
	AuditLogEntry,
	AuditProof,
	PolicyEvaluationTrace,
)

# Expose the Pydantic models as the primary API
from ambyte_schemas.models.common import (  # noqa: E402
	Actor,
	ActorType,
	ResourceIdentifier,
	RiskSeverity,
	SensitivityLevel,
	Tag,
)
from ambyte_schemas.models.dataset import (  # noqa: E402
	Dataset,
	DataSubjectType,
	LicenseInfo,
	PiiCategory,
	SchemaField,
)
from ambyte_schemas.models.lineage import (  # noqa: E402
	LineageEvent,
	ModelArtifact,
	ModelType,
	Run,
	RunType,
)
from ambyte_schemas.models.obligation import (  # noqa: E402
	AiModelConstraint,
	EnforcementLevel,
	GeofencingRule,
	Obligation,
	PrivacyEnhancementRule,
	PrivacyMethod,
	PurposeRestriction,
	RetentionRule,
	RetentionTrigger,
	SourceProvenance,
)

__all__ = [
	# Common
	'Actor',
	'ActorType',
	'ResourceIdentifier',
	'RiskSeverity',
	'SensitivityLevel',
	'Tag',
	# Dataset
	'DataSubjectType',
	'Dataset',
	'LicenseInfo',
	'PiiCategory',
	'SchemaField',
	# Lineage
	'LineageEvent',
	'ModelArtifact',
	'ModelType',
	'Run',
	'RunType',
	# Obligation
	'AiModelConstraint',
	'EnforcementLevel',
	'GeofencingRule',
	'Obligation',
	'PrivacyEnhancementRule',
	'PrivacyMethod',
	'PurposeRestriction',
	'RetentionRule',
	'RetentionTrigger',
	'SourceProvenance',
	# Audit
	'AuditLogEntry',
	'AuditBlockHeader',
	'AuditProof',
	'PolicyEvaluationTrace',
]
