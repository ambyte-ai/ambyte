from datetime import datetime
from enum import IntEnum
from typing import List, Optional

from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import Field

from ambyte_schemas.models.common import Actor, AmbyteBaseModel, RiskSeverity
from ambyte_schemas.proto.lineage.v1 import lineage_pb2

# ==============================================================================
# Enums
# ==============================================================================


class RunType(IntEnum):
	UNSPECIFIED = lineage_pb2.Run.RUN_TYPE_UNSPECIFIED
	ETL_TRANSFORM = lineage_pb2.Run.RUN_TYPE_ETL_TRANSFORM
	AI_TRAINING = lineage_pb2.Run.RUN_TYPE_AI_TRAINING
	AI_FINE_TUNING = lineage_pb2.Run.RUN_TYPE_AI_FINE_TUNING
	AI_RAG_QUERY = lineage_pb2.Run.RUN_TYPE_AI_RAG_QUERY
	HUMAN_DOWNLOAD = lineage_pb2.Run.RUN_TYPE_HUMAN_DOWNLOAD


class ModelType(IntEnum):
	UNSPECIFIED = lineage_pb2.ModelArtifact.MODEL_TYPE_UNSPECIFIED
	LLM = lineage_pb2.ModelArtifact.MODEL_TYPE_LLM
	COMPUTER_VISION = lineage_pb2.ModelArtifact.MODEL_TYPE_COMPUTER_VISION
	TABULAR_REGRESSOR = lineage_pb2.ModelArtifact.MODEL_TYPE_TABULAR_REGRESSOR
	EMBEDDING = lineage_pb2.ModelArtifact.MODEL_TYPE_EMBEDDING


# ==============================================================================
# Models
# ==============================================================================


class Run(AmbyteBaseModel):
	id: str
	type: RunType
	triggered_by: Optional[Actor] = None
	start_time: Optional[datetime] = None
	end_time: Optional[datetime] = None
	success: bool = False

	def to_proto(self) -> lineage_pb2.Run:
		start_ts = Timestamp()
		if self.start_time:
			start_ts.FromDatetime(self.start_time)

		end_ts = Timestamp()
		if self.end_time:
			end_ts.FromDatetime(self.end_time)

		return lineage_pb2.Run(
			id=self.id,
			type=self.type.value,
			triggered_by=self.triggered_by.to_proto() if self.triggered_by else None,
			start_time=start_ts if self.start_time else None,
			end_time=end_ts if self.end_time else None,
			success=self.success,
		)

	@classmethod
	def from_proto(cls, proto: lineage_pb2.Run) -> 'Run':
		return cls(
			id=proto.id,
			type=RunType(proto.type),
			triggered_by=Actor.from_proto(proto.triggered_by) if proto.HasField('triggered_by') else None,
			start_time=proto.start_time.ToDatetime() if proto.HasField('start_time') else None,
			end_time=proto.end_time.ToDatetime() if proto.HasField('end_time') else None,
			success=proto.success,
		)


class LineageEvent(AmbyteBaseModel):
	run_id: str
	input_urns: List[str] = Field(default_factory=list)
	output_urns: List[str] = Field(default_factory=list)

	def to_proto(self) -> lineage_pb2.LineageEvent:
		return lineage_pb2.LineageEvent(run_id=self.run_id, input_urns=self.input_urns, output_urns=self.output_urns)

	@classmethod
	def from_proto(cls, proto: lineage_pb2.LineageEvent) -> 'LineageEvent':
		return cls(run_id=proto.run_id, input_urns=list(proto.input_urns), output_urns=list(proto.output_urns))


class ModelArtifact(AmbyteBaseModel):
	id: str
	urn: str
	name: str
	version: str
	model_type: ModelType
	risk_level: RiskSeverity
	base_model_urn: str = ''

	def to_proto(self) -> lineage_pb2.ModelArtifact:
		return lineage_pb2.ModelArtifact(
			id=self.id,
			urn=self.urn,
			name=self.name,
			version=self.version,
			model_type=self.model_type.value,
			risk_level=self.risk_level.value,
			base_model_urn=self.base_model_urn,
		)

	@classmethod
	def from_proto(cls, proto: lineage_pb2.ModelArtifact) -> 'ModelArtifact':
		return cls(
			id=proto.id,
			urn=proto.urn,
			name=proto.name,
			version=proto.version,
			model_type=ModelType(proto.model_type),
			risk_level=RiskSeverity(proto.risk_level),
			base_model_urn=proto.base_model_urn,
		)
