"""
Tests for the LineageGraph class which analyzes dependency graphs via MetadataProvider.
"""

from typing import Any

import pytest
from ambyte_rules.interfaces import MetadataProvider
from ambyte_rules.lineage import LineageGraph
from ambyte_schemas.models.common import RiskSeverity, SensitivityLevel


class MockMetadataProvider(MetadataProvider):
	"""In-memory mock provider for testing."""

	def __init__(self, ancestors: dict[str, list[str]], metadata: dict[str, dict[str, Any]]):
		"""
		Args:
		    ancestors: Mapping of URN -> list of upstream ancestor URNs.
		    metadata: Mapping of URN -> metadata dict.
		"""
		self._ancestors = ancestors
		self._metadata = metadata

	async def get_node_metadata(self, urn: str) -> dict[str, Any]:
		return self._metadata.get(urn, {})

	async def get_upstream_ancestors(self, urn: str) -> list[str]:
		return self._ancestors.get(urn, [])


# ==============================================================================
# RISK PROPAGATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_get_inherited_risk_max_from_ancestors():
	"""
	Scenario:
	- Data A (Low Risk)
	- Data B (High Risk)
	- Model M trains on [A, B]
	- Result: Model M inherits High Risk (max of ancestors)
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:model:M': ['urn:data:A', 'urn:data:B'],
		},
		metadata={
			'urn:data:A': {'risk': RiskSeverity.LOW},
			'urn:data:B': {'risk': RiskSeverity.HIGH},
			'urn:model:M': {},  # No intrinsic risk
		},
	)
	graph = LineageGraph(provider)

	inherited_risk = await graph.get_inherited_risk('urn:model:M')
	assert inherited_risk == RiskSeverity.HIGH


@pytest.mark.asyncio
async def test_get_inherited_risk_includes_self():
	"""
	The target node's own risk should be included in the calculation.
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:model:M': ['urn:data:A'],
		},
		metadata={
			'urn:data:A': {'risk': RiskSeverity.LOW},
			'urn:model:M': {'risk': RiskSeverity.UNACCEPTABLE},  # Self has higher risk
		},
	)
	graph = LineageGraph(provider)

	inherited_risk = await graph.get_inherited_risk('urn:model:M')
	assert inherited_risk == RiskSeverity.UNACCEPTABLE


@pytest.mark.asyncio
async def test_get_inherited_risk_no_ancestors():
	"""
	A node with no ancestors should return its own risk or UNSPECIFIED.
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:standalone': [],
		},
		metadata={
			'urn:standalone': {'risk': RiskSeverity.MEDIUM},
		},
	)
	graph = LineageGraph(provider)

	inherited_risk = await graph.get_inherited_risk('urn:standalone')
	assert inherited_risk == RiskSeverity.MEDIUM


@pytest.mark.asyncio
async def test_get_inherited_risk_defaults_to_unspecified():
	"""
	If no risk is set anywhere, return UNSPECIFIED.
	"""
	provider = MockMetadataProvider(
		ancestors={'urn:empty': []},
		metadata={'urn:empty': {}},  # No risk key
	)
	graph = LineageGraph(provider)

	inherited_risk = await graph.get_inherited_risk('urn:empty')
	assert inherited_risk == RiskSeverity.UNSPECIFIED


# ==============================================================================
# SENSITIVITY PROPAGATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_get_inherited_sensitivity_chain():
	"""
	Scenario: Chain of custody
	- Raw (Confidential) -> Cleaned -> Aggregated
	- Result: Aggregated should inherit Confidential.
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:agg': ['urn:cleaned', 'urn:raw'],  # Full chain as ancestors
			'urn:cleaned': ['urn:raw'],
		},
		metadata={
			'urn:raw': {'sensitivity': SensitivityLevel.CONFIDENTIAL},
			'urn:cleaned': {},  # No explicit sensitivity
			'urn:agg': {},
		},
	)
	graph = LineageGraph(provider)

	sensitivity = await graph.get_inherited_sensitivity('urn:agg')
	assert sensitivity == SensitivityLevel.CONFIDENTIAL


@pytest.mark.asyncio
async def test_get_inherited_sensitivity_includes_self():
	"""
	The target node's own sensitivity should be included.
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:report': ['urn:data'],
		},
		metadata={
			'urn:data': {'sensitivity': SensitivityLevel.PUBLIC},
			'urn:report': {'sensitivity': SensitivityLevel.RESTRICTED},  # Higher
		},
	)
	graph = LineageGraph(provider)

	sensitivity = await graph.get_inherited_sensitivity('urn:report')
	assert sensitivity == SensitivityLevel.RESTRICTED


@pytest.mark.asyncio
async def test_get_inherited_sensitivity_defaults_to_unspecified():
	"""
	If no sensitivity is set anywhere, return UNSPECIFIED.
	"""
	provider = MockMetadataProvider(
		ancestors={'urn:empty': []},
		metadata={'urn:empty': {}},
	)
	graph = LineageGraph(provider)

	sensitivity = await graph.get_inherited_sensitivity('urn:empty')
	assert sensitivity == SensitivityLevel.UNSPECIFIED


# ==============================================================================
# AI POISON PILL TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_get_poisoned_constraints_identifies_blockers():
	"""
	Scenario:
	- Dataset A (Training Allowed)
	- Dataset B (Training FORBIDDEN)
	- Model M uses [A, B]
	- Result: Model M has 'B' as a poisoned source.
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:model:M': ['urn:data:A', 'urn:data:B'],
		},
		metadata={
			'urn:data:A': {'ai_training_allowed': True},
			'urn:data:B': {'ai_training_allowed': False},  # Poison pill
		},
	)
	graph = LineageGraph(provider)

	blockers = await graph.get_poisoned_constraints('urn:model:M')
	assert 'urn:data:B' in blockers
	assert 'urn:data:A' not in blockers


@pytest.mark.asyncio
async def test_get_poisoned_constraints_no_blockers():
	"""
	If all ancestors allow training, return empty list.
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:model:M': ['urn:data:A', 'urn:data:B'],
		},
		metadata={
			'urn:data:A': {'ai_training_allowed': True},
			'urn:data:B': {'ai_training_allowed': True},
		},
	)
	graph = LineageGraph(provider)

	blockers = await graph.get_poisoned_constraints('urn:model:M')
	assert blockers == []


@pytest.mark.asyncio
async def test_get_poisoned_constraints_missing_flag_defaults_to_allowed():
	"""
	If ai_training_allowed is not set, default to True (allowed).
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:model:M': ['urn:data:A'],
		},
		metadata={
			'urn:data:A': {},  # No ai_training_allowed key
		},
	)
	graph = LineageGraph(provider)

	blockers = await graph.get_poisoned_constraints('urn:model:M')
	assert blockers == []


@pytest.mark.asyncio
async def test_get_poisoned_constraints_does_not_check_self():
	"""
	Poison check is only for ancestors, not the target node itself.
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:model:M': [],  # No ancestors
		},
		metadata={
			'urn:model:M': {'ai_training_allowed': False},  # Self is forbidden
		},
	)
	graph = LineageGraph(provider)

	blockers = await graph.get_poisoned_constraints('urn:model:M')
	# Self is not included in ancestor poison check
	assert blockers == []


@pytest.mark.asyncio
async def test_get_poisoned_constraints_multiple_blockers():
	"""
	Multiple ancestors can be poisoned.
	"""
	provider = MockMetadataProvider(
		ancestors={
			'urn:model:M': ['urn:data:A', 'urn:data:B', 'urn:data:C'],
		},
		metadata={
			'urn:data:A': {'ai_training_allowed': False},
			'urn:data:B': {'ai_training_allowed': True},
			'urn:data:C': {'ai_training_allowed': False},
		},
	)
	graph = LineageGraph(provider)

	blockers = await graph.get_poisoned_constraints('urn:model:M')
	assert len(blockers) == 2
	assert 'urn:data:A' in blockers
	assert 'urn:data:C' in blockers
