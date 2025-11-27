from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChangeType(str, Enum):
	ADDED = 'ADDED'  # Field was None, now has value
	REMOVED = 'REMOVED'  # Field had value, now None
	MODIFIED = 'MODIFIED'  # Value changed
	NO_CHANGE = 'NO_CHANGE'


class ChangeImpact(str, Enum):
	RESTRICTIVE = 'RESTRICTIVE'  # Tighter controls (e.g., Duration reduced) -> Safer but operational impact
	PERMISSIVE = 'PERMISSIVE'  # Looser controls (e.g., Region added) -> Riskier
	NEUTRAL = 'NEUTRAL'  # Text changes, metadata


class DiffItem(BaseModel):
	"""
	Represents a single atomic change in the policy.
	"""

	category: str  # e.g., "Retention", "Geofencing", "AI"
	field: str  # e.g., "duration", "allowed_regions"
	old_value: Any
	new_value: Any
	change_type: ChangeType
	impact: ChangeImpact
	description: str  # Human-readable summary of this specific line item


class PolicyDiffReport(BaseModel):
	"""
	The full report comparison between two ResolvedPolicy objects.
	"""

	resource_urn: str
	old_obligation_ids: list[str]
	new_obligation_ids: list[str]

	changes: list[DiffItem] = Field(default_factory=list)

	@property
	def has_changes(self) -> bool:
		return len(self.changes) > 0

	@property
	def risk_score_delta(self) -> int:
		"""
		Rough heuristic: Positive means we got riskier (permissive),
		Negative means we got stricter.
		"""
		score = 0
		for c in self.changes:
			if c.impact == ChangeImpact.PERMISSIVE:
				score += 1
			elif c.impact == ChangeImpact.RESTRICTIVE:
				score -= 1
		return score

	def to_markdown(self) -> str:
		if not self.changes:
			return f'✅ **No Material Changes** detected for `{self.resource_urn}`.'

		lines = [f'### 📋 Policy Diff Report for `{self.resource_urn}`']

		# Risk Header
		score = self.risk_score_delta
		if score > 0:
			lines.append(f'> ⚠️ **Risk Profile Increased:** Policy has become more permissive (+{score}).')
		elif score < 0:
			lines.append(f'> 🛡️ **Risk Profile Decreased:** Policy has become stricter ({score}).')
		else:
			lines.append('> ℹ️ **Risk Profile Neutral:** Policy structure changed but risk level is balanced.')

		lines.append('')
		lines.append('| Category | Impact | Change | Description |')
		lines.append('| :--- | :--- | :--- | :--- |')

		icon_map = {
			ChangeImpact.PERMISSIVE: '🔓 (Looser)',
			ChangeImpact.RESTRICTIVE: '🔒 (Stricter)',
			ChangeImpact.NEUTRAL: '📝 (Info)',
		}

		for c in self.changes:
			icon = icon_map[c.impact]
			lines.append(f'| **{c.category}** | {icon} | `{c.field}` | {c.description} |')

		lines.append('')
		lines.append(
			f'**Contributing Obligations:** {len(self.new_obligation_ids)} (Was: {len(self.old_obligation_ids)})'
		)

		return '\n'.join(lines)
