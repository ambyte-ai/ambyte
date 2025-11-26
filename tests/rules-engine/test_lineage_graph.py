from ambyte_rules.lineage import LineageGraph
from ambyte_schemas.models.common import RiskSeverity, SensitivityLevel
from ambyte_schemas.models.lineage import LineageEvent


def test_risk_propagation_max():
	"""
	Scenario:
	- Data A (Low Risk)
	- Data B (High Risk)
	- Model M trains on [A, B]
	- Result: Model M is High Risk
	"""
	graph = LineageGraph()

	# Define Lineage
	event = LineageEvent(run_id='run_1', input_urns=['urn:data:A', 'urn:data:B'], output_urns=['urn:model:M'])
	graph.add_event(event)

	# Define Attributes
	graph.set_node_risk('urn:data:A', RiskSeverity.LOW)
	graph.set_node_risk('urn:data:B', RiskSeverity.HIGH)

	# Check inheritance
	inherited_risk = graph.get_inherited_risk('urn:model:M')
	assert inherited_risk == RiskSeverity.HIGH


def test_sensitivity_propagation_chain():
	"""
	Scenario: Chain of custody
	- Raw (Confidential) -> Cleaned -> Aggregated -> Report
	- Result: Report should be Confidential.
	"""
	graph = LineageGraph()

	# Raw -> Cleaned
	graph.add_event(LineageEvent(run_id='1', input_urns=['raw'], output_urns=['cleaned']))
	# Cleaned -> Aggregated
	graph.add_event(LineageEvent(run_id='2', input_urns=['cleaned'], output_urns=['agg']))

	graph.set_node_sensitivity('raw', SensitivityLevel.CONFIDENTIAL)
	# Even if 'cleaned' isn't explicitly tagged, it inherits.

	assert graph.get_inherited_sensitivity('agg') == SensitivityLevel.CONFIDENTIAL


def test_ai_poison_pill():
	"""
	Scenario:
	- Dataset A (Training Allowed)
	- Dataset B (Training FORBIDDEN)
	- Model M uses [A, B]
	- Result: Model M has a 'poisoned' lineage.
	"""
	graph = LineageGraph()
	graph.add_event(LineageEvent(run_id='1', input_urns=['A', 'B'], output_urns=['M']))

	# Set metadata directly for this test
	graph.node_metadata['A'] = {'ai_training_allowed': True}
	graph.node_metadata['B'] = {'ai_training_allowed': False}

	blockers = graph.get_poisoned_constraints('M')
	assert 'B' in blockers
	assert 'A' not in blockers
