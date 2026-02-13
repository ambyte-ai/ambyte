from datetime import datetime, timedelta
from enum import IntEnum
from typing import Any, cast

from google.protobuf.duration_pb2 import Duration
from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import Field

from ambyte_schemas.models.common import AmbyteBaseModel
from ambyte_schemas.proto.obligation.v1 import obligation_pb2

# ==============================================================================
# Enums
# ==============================================================================


class EnforcementLevel(IntEnum):
	UNSPECIFIED = obligation_pb2.ENFORCEMENT_LEVEL_UNSPECIFIED
	BLOCKING = obligation_pb2.ENFORCEMENT_LEVEL_BLOCKING
	AUDIT_ONLY = obligation_pb2.ENFORCEMENT_LEVEL_AUDIT_ONLY
	NOTIFY_HUMAN = obligation_pb2.ENFORCEMENT_LEVEL_NOTIFY_HUMAN


class RetentionTrigger(IntEnum):
	UNSPECIFIED = obligation_pb2.RetentionRule.RETENTION_TRIGGER_UNSPECIFIED
	CREATION_DATE = obligation_pb2.RetentionRule.RETENTION_TRIGGER_CREATION_DATE
	LAST_ACCESS_DATE = obligation_pb2.RetentionRule.RETENTION_TRIGGER_LAST_ACCESS_DATE
	EVENT_DATE = obligation_pb2.RetentionRule.RETENTION_TRIGGER_EVENT_DATE
	DATA_SUBJECT_REQUEST = obligation_pb2.RetentionRule.RETENTION_TRIGGER_DATA_SUBJECT_REQUEST


class PrivacyMethod(IntEnum):
	UNSPECIFIED = obligation_pb2.PrivacyEnhancementRule.PRIVACY_METHOD_UNSPECIFIED
	PSEUDONYMIZATION = obligation_pb2.PrivacyEnhancementRule.PRIVACY_METHOD_PSEUDONYMIZATION
	ANONYMIZATION = obligation_pb2.PrivacyEnhancementRule.PRIVACY_METHOD_ANONYMIZATION
	DIFFERENTIAL_PRIVACY = obligation_pb2.PrivacyEnhancementRule.PRIVACY_METHOD_DIFFERENTIAL_PRIVACY
	ROW_LEVEL_SECURITY = obligation_pb2.PrivacyEnhancementRule.PRIVACY_METHOD_ROW_LEVEL_SECURITY


# ==============================================================================
# Constraint Models
# ==============================================================================


class RetentionRule(AmbyteBaseModel):
	duration: timedelta
	trigger: RetentionTrigger
	allow_legal_hold_override: bool = False

	def to_proto(self) -> obligation_pb2.RetentionRule:
		dur_proto = Duration()
		dur_proto.FromTimedelta(self.duration)

		return obligation_pb2.RetentionRule(
			duration=dur_proto,
			trigger=cast(Any, self.trigger),
			allow_legal_hold_override=self.allow_legal_hold_override,
		)

	@classmethod
	def from_proto(cls, proto: obligation_pb2.RetentionRule) -> 'RetentionRule':
		return cls(
			duration=proto.duration.ToTimedelta(),
			trigger=RetentionTrigger(proto.trigger),
			allow_legal_hold_override=proto.allow_legal_hold_override,
		)


class GeofencingRule(AmbyteBaseModel):
	allowed_regions: list[str] = Field(default_factory=list)
	denied_regions: list[str] = Field(default_factory=list)
	strict_residency: bool = False

	def to_proto(self) -> obligation_pb2.GeofencingRule:
		return obligation_pb2.GeofencingRule(
			allowed_regions=self.allowed_regions,
			denied_regions=self.denied_regions,
			strict_residency=self.strict_residency,
		)

	@classmethod
	def from_proto(cls, proto: obligation_pb2.GeofencingRule) -> 'GeofencingRule':
		return cls(
			allowed_regions=list(proto.allowed_regions),
			denied_regions=list(proto.denied_regions),
			strict_residency=proto.strict_residency,
		)


class PurposeRestriction(AmbyteBaseModel):
	allowed_purposes: list[str] = Field(default_factory=list)
	denied_purposes: list[str] = Field(default_factory=list)

	def to_proto(self) -> obligation_pb2.PurposeRestriction:
		return obligation_pb2.PurposeRestriction(
			allowed_purposes=self.allowed_purposes, denied_purposes=self.denied_purposes
		)

	@classmethod
	def from_proto(cls, proto: obligation_pb2.PurposeRestriction) -> 'PurposeRestriction':
		return cls(allowed_purposes=list(proto.allowed_purposes), denied_purposes=list(proto.denied_purposes))


class PrivacyEnhancementRule(AmbyteBaseModel):
	method: PrivacyMethod
	parameters: dict[str, str] = Field(default_factory=dict)

	def to_proto(self) -> obligation_pb2.PrivacyEnhancementRule:
		return obligation_pb2.PrivacyEnhancementRule(method=cast(Any, self.method), parameters=self.parameters)

	@classmethod
	def from_proto(cls, proto: obligation_pb2.PrivacyEnhancementRule) -> 'PrivacyEnhancementRule':
		return cls(method=PrivacyMethod(proto.method), parameters=dict(proto.parameters))


class AiModelConstraint(AmbyteBaseModel):
	training_allowed: bool = False
	fine_tuning_allowed: bool = False
	rag_usage_allowed: bool = False
	requires_open_source_release: bool = False
	attribution_text_required: str = ''

	def to_proto(self) -> obligation_pb2.AiModelConstraint:
		return obligation_pb2.AiModelConstraint(
			training_allowed=self.training_allowed,
			fine_tuning_allowed=self.fine_tuning_allowed,
			rag_usage_allowed=self.rag_usage_allowed,
			requires_open_source_release=self.requires_open_source_release,
			attribution_text_required=self.attribution_text_required,
		)

	@classmethod
	def from_proto(cls, proto: obligation_pb2.AiModelConstraint) -> 'AiModelConstraint':
		return cls(
			training_allowed=proto.training_allowed,
			fine_tuning_allowed=proto.fine_tuning_allowed,
			rag_usage_allowed=proto.rag_usage_allowed,
			requires_open_source_release=proto.requires_open_source_release,
			attribution_text_required=proto.attribution_text_required,
		)


class SourceProvenance(AmbyteBaseModel):
	source_id: str
	document_type: str
	section_reference: str = ''
	document_uri: str = ''

	def to_proto(self) -> obligation_pb2.SourceProvenance:
		return obligation_pb2.SourceProvenance(
			source_id=self.source_id,
			document_type=self.document_type,
			section_reference=self.section_reference,
			document_uri=self.document_uri,
		)

	@classmethod
	def from_proto(cls, proto: obligation_pb2.SourceProvenance) -> 'SourceProvenance':
		return cls(
			source_id=proto.source_id,
			document_type=proto.document_type,
			section_reference=proto.section_reference,
			document_uri=proto.document_uri,
		)


class ResourceSelector(AmbyteBaseModel):
	"""
	Defines scope: URN patterns and Tags used to match resources.
	"""

	include_patterns: list[str] = Field(default_factory=list)
	exclude_patterns: list[str] = Field(default_factory=list)
	match_tags: dict[str, str] = Field(default_factory=dict)

	def to_proto(self) -> obligation_pb2.ResourceSelector:
		return obligation_pb2.ResourceSelector(
			include_patterns=self.include_patterns,
			exclude_patterns=self.exclude_patterns,
			match_tags=self.match_tags,
		)

	@classmethod
	def from_proto(cls, proto: obligation_pb2.ResourceSelector) -> 'ResourceSelector':
		return cls(
			include_patterns=list(proto.include_patterns),
			exclude_patterns=list(proto.exclude_patterns),
			match_tags=dict(proto.match_tags),
		)


# ==============================================================================
# Main Model
# ==============================================================================


class Obligation(AmbyteBaseModel):
	id: str
	title: str
	description: str
	provenance: SourceProvenance
	enforcement_level: EnforcementLevel = EnforcementLevel.AUDIT_ONLY
	target: ResourceSelector = Field(default_factory=ResourceSelector)
	is_active: bool = True

	retention: RetentionRule | None = None
	geofencing: GeofencingRule | None = None
	purpose: PurposeRestriction | None = None
	privacy: PrivacyEnhancementRule | None = None
	ai_model: AiModelConstraint | None = None

	created_at: datetime | None = None
	updated_at: datetime | None = None

	def to_proto(self) -> obligation_pb2.Obligation:
		# Handle Timestamps
		created_ts = Timestamp()
		if self.created_at:
			created_ts.FromDatetime(self.created_at)

		updated_ts = Timestamp()
		if self.updated_at:
			updated_ts.FromDatetime(self.updated_at)

		target_selector: ResourceSelector = self.target

		# Build the base object
		obj = obligation_pb2.Obligation(
			id=self.id,
			title=self.title,
			description=self.description,
			provenance=self.provenance.to_proto(),
			enforcement_level=cast(Any, self.enforcement_level),
			target=target_selector.to_proto(),  # pylint: disable=E1101
			is_active=self.is_active,
			created_at=created_ts if self.created_at else None,
			updated_at=updated_ts if self.updated_at else None,
		)

		# Set the OneOf field
		if self.retention:
			obj.retention.CopyFrom(self.retention.to_proto())
		elif self.geofencing:
			obj.geofencing.CopyFrom(self.geofencing.to_proto())
		elif self.purpose:
			obj.purpose.CopyFrom(self.purpose.to_proto())
		elif self.privacy:
			obj.privacy.CopyFrom(self.privacy.to_proto())
		elif self.ai_model:
			obj.ai_model.CopyFrom(self.ai_model.to_proto())

		return obj

	@classmethod
	def from_proto(cls, proto: obligation_pb2.Obligation) -> 'Obligation':
		# Identify which OneOf is set
		which_constraint = proto.WhichOneof('constraint')

		return cls(
			id=proto.id,
			title=proto.title,
			description=proto.description,
			provenance=SourceProvenance.from_proto(proto.provenance),
			enforcement_level=EnforcementLevel(proto.enforcement_level),
			target=ResourceSelector.from_proto(proto.target) if proto.HasField('target') else ResourceSelector(),
			is_active=proto.is_active,
			# Map the active constraint
			retention=RetentionRule.from_proto(proto.retention) if which_constraint == 'retention' else None,
			geofencing=GeofencingRule.from_proto(proto.geofencing) if which_constraint == 'geofencing' else None,
			purpose=PurposeRestriction.from_proto(proto.purpose) if which_constraint == 'purpose' else None,
			privacy=PrivacyEnhancementRule.from_proto(proto.privacy) if which_constraint == 'privacy' else None,
			ai_model=AiModelConstraint.from_proto(proto.ai_model) if which_constraint == 'ai_model' else None,
			created_at=proto.created_at.ToDatetime() if proto.HasField('created_at') else None,
			updated_at=proto.updated_at.ToDatetime() if proto.HasField('updated_at') else None,
		)
