from enum import IntEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from ambyte_schemas.proto.common.v1 import common_pb2


class AmbyteBaseModel(BaseModel):
	"""
	Base configuration for all Ambyte Pydantic models.
	Enables working with ORMs and arbitrary types if needed.
	"""

	model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# ==============================================================================
# Enums (Mapped strictly to Protobuf integer values)
# ==============================================================================


class SensitivityLevel(IntEnum):
	UNSPECIFIED = common_pb2.SENSITIVITY_LEVEL_UNSPECIFIED
	PUBLIC = common_pb2.SENSITIVITY_LEVEL_PUBLIC
	INTERNAL = common_pb2.SENSITIVITY_LEVEL_INTERNAL
	CONFIDENTIAL = common_pb2.SENSITIVITY_LEVEL_CONFIDENTIAL
	RESTRICTED = common_pb2.SENSITIVITY_LEVEL_RESTRICTED


class RiskSeverity(IntEnum):
	UNSPECIFIED = common_pb2.RISK_SEVERITY_UNSPECIFIED
	LOW = common_pb2.RISK_SEVERITY_LOW
	MEDIUM = common_pb2.RISK_SEVERITY_MEDIUM
	HIGH = common_pb2.RISK_SEVERITY_HIGH
	UNACCEPTABLE = common_pb2.RISK_SEVERITY_UNACCEPTABLE


class ActorType(IntEnum):
	UNSPECIFIED = common_pb2.Actor.ACTOR_TYPE_UNSPECIFIED
	HUMAN = common_pb2.Actor.ACTOR_TYPE_HUMAN
	SERVICE_ACCOUNT = common_pb2.Actor.ACTOR_TYPE_SERVICE_ACCOUNT
	SYSTEM_INTERNAL = common_pb2.Actor.ACTOR_TYPE_SYSTEM_INTERNAL


# ==============================================================================
# Models
# ==============================================================================


class Tag(AmbyteBaseModel):
	key: str
	value: str

	def to_proto(self) -> common_pb2.Tag:
		return common_pb2.Tag(key=self.key, value=self.value)

	@classmethod
	def from_proto(cls, proto: common_pb2.Tag) -> 'Tag':
		return cls(key=proto.key, value=proto.value)


class ResourceIdentifier(AmbyteBaseModel):
	platform: str
	location: str
	native_id: str = ''

	def to_proto(self) -> common_pb2.ResourceIdentifier:
		return common_pb2.ResourceIdentifier(platform=self.platform, location=self.location, native_id=self.native_id)

	@classmethod
	def from_proto(cls, proto: common_pb2.ResourceIdentifier) -> 'ResourceIdentifier':
		return cls(platform=proto.platform, location=proto.location, native_id=proto.native_id)


class Actor(AmbyteBaseModel):
	id: str
	type: ActorType
	roles: list[str] = Field(default_factory=list)
	attributes: dict[str, str] = Field(default_factory=dict)

	def to_proto(self) -> common_pb2.Actor:
		return common_pb2.Actor(id=self.id, type=cast(Any, self.type), roles=self.roles, attributes=self.attributes)

	@classmethod
	def from_proto(cls, proto: common_pb2.Actor) -> 'Actor':
		return cls(id=proto.id, type=ActorType(proto.type), roles=list(proto.roles), attributes=dict(proto.attributes))
