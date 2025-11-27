from typing import Any

import networkx as nx
from ambyte_schemas.models.common import RiskSeverity, SensitivityLevel
from ambyte_schemas.models.lineage import LineageEvent


class LineageGraph:
	"""
	Manages the dependency graph of Data and Models.
	Used to calculate inherited properties (Risk, Sensitivity) from upstream sources.
	"""

	def __init__(self):
		# A Directed Acyclic Graph (DAG) where nodes are URNs
		self.graph = nx.DiGraph()

		# Local cache of node attributes (e.g. {'urn:1': {'risk': 3}})
		# In a real system, this would be fetched from the Control Plane DB.
		self.node_metadata: dict[str, dict[str, Any]] = {}

	def add_event(self, event: LineageEvent):
		"""
		Ingests a lineage event (Run) and updates the graph edges.
		"""
		for input_urn in event.input_urns:
			for output_urn in event.output_urns:
				self.graph.add_edge(input_urn, output_urn, run_id=event.run_id)

	def set_node_risk(self, urn: str, risk: RiskSeverity):
		if urn not in self.node_metadata:
			self.node_metadata[urn] = {}
		self.node_metadata[urn]['risk'] = risk

	def set_node_sensitivity(self, urn: str, sensitivity: SensitivityLevel):
		if urn not in self.node_metadata:
			self.node_metadata[urn] = {}
		self.node_metadata[urn]['sensitivity'] = sensitivity

	def get_inherited_risk(self, target_urn: str) -> RiskSeverity:
		"""
		Walks upstream to find the MAXIMUM risk level of any ancestor.

		Logic: A model trained on High Risk data is High Risk.
		"""
		# 1. Get all ancestors (recursive upstream dependencies)
		try:
			ancestors = nx.ancestors(self.graph, target_urn)
		except nx.NetworkXError:
			# Node might not exist in graph yet
			return RiskSeverity.UNSPECIFIED

		# 2. Include the node itself (in case it has intrinsic risk explicitly set)
		nodes_to_check = ancestors.union({target_urn})

		max_risk = RiskSeverity.UNSPECIFIED

		for node in nodes_to_check:
			meta = self.node_metadata.get(node, {})
			risk = meta.get('risk', RiskSeverity.UNSPECIFIED)
			if risk > max_risk:
				max_risk = risk

		return max_risk

	def get_inherited_sensitivity(self, target_urn: str) -> SensitivityLevel:
		"""
		Walks upstream to find the MAXIMUM sensitivity.

		Logic: Mixing Public data with Confidential data results in Confidential data.
		"""
		try:
			ancestors = nx.ancestors(self.graph, target_urn)
		except nx.NetworkXError:
			return SensitivityLevel.UNSPECIFIED

		nodes_to_check = ancestors.union({target_urn})
		max_sens = SensitivityLevel.UNSPECIFIED

		for node in nodes_to_check:
			meta = self.node_metadata.get(node, {})
			sens = meta.get('sensitivity', SensitivityLevel.UNSPECIFIED)
			if sens > max_sens:
				max_sens = sens

		return max_sens

	def get_poisoned_constraints(self, target_urn: str) -> list[str]:
		"""
		Identifies upstream nodes that explicitly FORBID downstream usage.

		Example: If Dataset A has 'ai_training_allowed=False', and Target B
		is a descendant, return A's URN as a blocker.
		"""
		try:
			ancestors = nx.ancestors(self.graph, target_urn)
		except nx.NetworkXError:
			return []

		poison_sources = []
		for node in ancestors:
			meta = self.node_metadata.get(node, {})
			# Check explicit flag. Default to True (Allowed) if not set.
			# Only if explicitly False do we flag it.
			if meta.get('ai_training_allowed') is False:
				poison_sources.append(node)

		return poison_sources
