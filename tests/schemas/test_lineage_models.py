from datetime import datetime, timedelta, timezone

from ambyte_schemas.models.common import RiskSeverity
from ambyte_schemas.models.lineage import (
	LineageEvent,
	ModelArtifact,
	ModelType,
	Run,
	RunType,
)
from ambyte_schemas.proto.lineage.v1 import lineage_pb2

# ==============================================================================
# RUN MODEL TESTS
# ==============================================================================


def test_run_initialization_defaults():
	"""Test that a Run initializes with expected defaults."""
	run = Run(id='run_123', type=RunType.ETL_TRANSFORM)

	assert run.id == 'run_123'
	assert run.type == RunType.ETL_TRANSFORM
	assert run.success is False  # Default
	assert run.triggered_by is None
	assert run.start_time is None
	assert run.end_time is None


def test_run_timestamps_and_actor(sample_actor):
	"""Test fully populated Run with timestamps and actor."""
	now = datetime.now(timezone.utc)
	later = now + timedelta(minutes=5)

	run = Run(
		id='run_complete',
		type=RunType.AI_TRAINING,
		triggered_by=sample_actor,
		start_time=now,
		end_time=later,
		success=True,
	)

	assert run.triggered_by.id == sample_actor.id
	assert run.success is True
	# Sanity check on time (Pydantic keeps them as datetime objects)
	assert run.end_time > run.start_time


def test_run_proto_roundtrip(sample_actor):
	"""
	Test Pydantic -> Proto -> Pydantic for Run.
	Ensures Enums and Timestamps survive the trip.
	"""
	start = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
	run = Run(id='run_proto_test', type=RunType.AI_RAG_QUERY, triggered_by=sample_actor, start_time=start, success=True)

	# 1. To Proto
	proto = run.to_proto()
	assert isinstance(proto, lineage_pb2.Run)
	assert proto.id == 'run_proto_test'
	assert proto.type == lineage_pb2.Run.RUN_TYPE_AI_RAG_QUERY
	assert proto.success is True
	assert proto.start_time.seconds > 0

	# 2. From Proto
	reconstructed = Run.from_proto(proto)

	# 3. Assertions
	assert reconstructed.id == run.id
	assert reconstructed.type == run.type
	# Compare Actor ID as deep object comparison works too
	assert reconstructed.triggered_by.id == sample_actor.id
	assert reconstructed.start_time == start


# ==============================================================================
# LINEAGE EVENT TESTS
# ==============================================================================


def test_lineage_event_graph_integrity():
	"""Test that LineageEvent correctly maps inputs to outputs."""
	event = LineageEvent(
		run_id='run_xyz',
		input_urns=['urn:s3:raw_data', 'urn:snowflake:dimensions'],
		output_urns=['urn:s3:processed_data'],
	)

	assert len(event.input_urns) == 2
	assert len(event.output_urns) == 1
	assert 'urn:s3:raw_data' in event.input_urns


def test_lineage_event_proto_roundtrip():
	event = LineageEvent(run_id='run_ABC', input_urns=['in_1'], output_urns=[])

	proto = event.to_proto()
	assert proto.run_id == 'run_ABC'
	# Proto repeated fields are list-like
	assert proto.input_urns == ['in_1']
	assert len(proto.output_urns) == 0

	reconstructed = LineageEvent.from_proto(proto)
	assert reconstructed == event


# ==============================================================================
# MODEL ARTIFACT TESTS
# ==============================================================================


def test_model_artifact_enums():
	"""Test ModelArtifact with ModelType and RiskSeverity Enums."""
	artifact = ModelArtifact(
		id='model_v1',
		urn='urn:model:gpt-finetune',
		name='Finance GPT',
		version='1.0.0',
		model_type=ModelType.LLM,
		risk_level=RiskSeverity.HIGH,
		base_model_urn='urn:model:llama-3',
	)

	assert artifact.model_type == ModelType.LLM
	assert artifact.risk_level == RiskSeverity.HIGH
	assert artifact.base_model_urn == 'urn:model:llama-3'


def test_model_artifact_proto_roundtrip():
	artifact = ModelArtifact(
		id='model_cv_1',
		urn='urn:model:yolo',
		name='Object Detection',
		version='v8',
		model_type=ModelType.COMPUTER_VISION,
		risk_level=RiskSeverity.LOW,
	)

	# 1. To Proto
	proto = artifact.to_proto()
	assert proto.model_type == lineage_pb2.ModelArtifact.MODEL_TYPE_COMPUTER_VISION
	assert proto.risk_level == 1  # RISK_SEVERITY_LOW

	# 2. From Proto
	reconstructed = ModelArtifact.from_proto(proto)

	assert reconstructed.model_type == ModelType.COMPUTER_VISION
	assert reconstructed.risk_level == RiskSeverity.LOW
	assert reconstructed.name == 'Object Detection'
