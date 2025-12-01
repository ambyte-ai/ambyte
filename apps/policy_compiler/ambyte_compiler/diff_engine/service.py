from typing import Any

from ambyte_rules.models import (
	EffectiveAiRules,
	EffectiveGeofencing,
	EffectivePrivacy,
	EffectivePurpose,
	EffectiveRetention,
	ResolvedPolicy,
)

from apps.policy_compiler.ambyte_compiler.diff_engine.models import (
	ChangeImpact,
	ChangeType,
	DiffItem,
	PolicyDiffReport,
)


class SemanticDiffEngine:
	"""
	Compares two ResolvedPolicy objects to generate a semantic difference report.
	"""

	def compute_diff(self, old: ResolvedPolicy, new: ResolvedPolicy) -> PolicyDiffReport:
		report = PolicyDiffReport(
			resource_urn=new.resource_urn,
			old_obligation_ids=old.contributing_obligation_ids,
			new_obligation_ids=new.contributing_obligation_ids,
		)

		# 1. Diff Retention
		self._diff_retention(old.retention, new.retention, report)

		# 2. Diff Geofencing
		self._diff_geofencing(old.geofencing, new.geofencing, report)

		# 3. Diff AI Rules
		self._diff_ai(old.ai_rules, new.ai_rules, report)

		# 4. Diff Purpose Restrictions
		self._diff_purpose(old.purpose, new.purpose, report)

		# 5. Diff Privacy Methods
		self._diff_privacy(old.privacy, new.privacy, report)

		return report

	def _diff_retention(self, old: EffectiveRetention | None, new: EffectiveRetention | None, report: PolicyDiffReport):
		if old == new:
			return

		# Case: Removed (Was present, now None) -> Indefinite/Unknown (Usually Permissive/Riskier)
		if old and not new:
			report.changes.append(
				DiffItem(
					category='Retention',
					field='rule',
					old_value='Defined',
					new_value='None',
					change_type=ChangeType.REMOVED,
					impact=ChangeImpact.PERMISSIVE,
					description='Retention rule removed. Data may be kept indefinitely.',
				)
			)
			return

		# Case: Added (Was None, now Defined) -> Restrictive
		if not old and new:
			report.changes.append(
				DiffItem(
					category='Retention',
					field='rule',
					old_value='None',
					new_value=str(new.duration),
					change_type=ChangeType.ADDED,
					impact=ChangeImpact.RESTRICTIVE,
					description=f'Retention rule added. Max duration: {new.duration}.',
				)
			)
			return

		# Case: Modified
		if old and new:
			# 1. Indefinite Flag
			if old.is_indefinite != new.is_indefinite:
				impact = ChangeImpact.PERMISSIVE if new.is_indefinite else ChangeImpact.RESTRICTIVE
				report.changes.append(
					DiffItem(
						category='Retention',
						field='is_indefinite',
						old_value=old.is_indefinite,
						new_value=new.is_indefinite,
						change_type=ChangeType.MODIFIED,
						impact=impact,
						description=f'Legal Hold (Indefinite) changed from {old.is_indefinite} to {new.is_indefinite}.',
					)
				)

			# 2. Duration
			if old.duration != new.duration:
				# Shorter duration = Restrictive (Good for privacy, hard for business)
				# Longer duration = Permissive
				impact = ChangeImpact.RESTRICTIVE if new.duration < old.duration else ChangeImpact.PERMISSIVE
				report.changes.append(
					DiffItem(
						category='Retention',
						field='duration',
						old_value=str(old.duration),
						new_value=str(new.duration),
						change_type=ChangeType.MODIFIED,
						impact=impact,
						description=f'Retention duration changed from {old.duration} to {new.duration}.',
					)
				)

	def _diff_geofencing(
		self, old: EffectiveGeofencing | None, new: EffectiveGeofencing | None, report: PolicyDiffReport
	):
		if old == new:
			return

		if not old and new:
			report.changes.append(
				DiffItem(
					category='Geofencing',
					field='rule',
					old_value='None',
					new_value='Defined',
					change_type=ChangeType.ADDED,
					impact=ChangeImpact.RESTRICTIVE,
					description='Geofencing rules applied.',
				)
			)
			return

		if old and new:
			# 1. Global Ban
			if old.is_global_ban != new.is_global_ban:
				impact = ChangeImpact.RESTRICTIVE if new.is_global_ban else ChangeImpact.PERMISSIVE
				report.changes.append(
					DiffItem(
						category='Geofencing',
						field='is_global_ban',
						old_value=old.is_global_ban,
						new_value=new.is_global_ban,
						change_type=ChangeType.MODIFIED,
						impact=impact,
						description=f'Global Data Ban changed to {new.is_global_ban}.',
					)
				)

			# 2. Allowed Regions (Set Logic)
			# Added Regions = Permissive
			# Removed Regions = Restrictive
			added = new.allowed_regions - old.allowed_regions
			removed = old.allowed_regions - new.allowed_regions

			if added:
				report.changes.append(
					DiffItem(
						category='Geofencing',
						field='allowed_regions',
						old_value=None,
						new_value=list(added),
						change_type=ChangeType.MODIFIED,
						impact=ChangeImpact.PERMISSIVE,
						description=f'Allowed regions added: {", ".join(added)}',
					)
				)

			if removed:
				report.changes.append(
					DiffItem(
						category='Geofencing',
						field='allowed_regions',
						old_value=list(removed),
						new_value=None,
						change_type=ChangeType.MODIFIED,
						impact=ChangeImpact.RESTRICTIVE,
						description=f'Allowed regions removed: {", ".join(removed)}',
					)
				)

	def _diff_ai(self, old: EffectiveAiRules | None, new: EffectiveAiRules | None, report: PolicyDiffReport):
		if old == new:
			return

		# Helper for boolean flips
		def check_bool(field: str, label: str, reverse_impact=False):
			val_old = getattr(old, field, None)
			val_new = getattr(new, field, None)

			if val_old is not None and val_new is not None and val_old != val_new:
				# Normal: False -> True is Permissive (e.g. Training Allowed)
				# Reverse: False -> True is Restrictive (e.g. Attribution Required)
				if reverse_impact:
					impact = ChangeImpact.RESTRICTIVE if val_new else ChangeImpact.PERMISSIVE
				else:
					impact = ChangeImpact.PERMISSIVE if val_new else ChangeImpact.RESTRICTIVE

				report.changes.append(
					DiffItem(
						category='AI Rules',
						field=field,
						old_value=val_old,
						new_value=val_new,
						change_type=ChangeType.MODIFIED,
						impact=impact,
						description=f'{label} changed from {val_old} to {val_new}.',
					)
				)

		if old and new:
			check_bool('training_allowed', 'AI Training')
			check_bool('fine_tuning_allowed', 'AI Fine-Tuning')
			check_bool('rag_allowed', 'RAG Usage')
			check_bool('attribution_required', 'Attribution Requirement', reverse_impact=True)

			if old.attribution_text != new.attribution_text:
				report.changes.append(
					DiffItem(
						category='AI Rules',
						field='attribution_text',
						old_value=old.attribution_text,
						new_value=new.attribution_text,
						change_type=ChangeType.MODIFIED,
						impact=ChangeImpact.NEUTRAL,
						description='Attribution text content updated.',
					)
				)

	def _diff_purpose(self, old: EffectivePurpose | None, new: EffectivePurpose | None, report: PolicyDiffReport):
		if old == new:
			return

		# Case: Added Purpose Restrictions (Was open, now restricted) -> Restrictive
		if not old and new:
			report.changes.append(
				DiffItem(
					category='Purpose',
					field='rule',
					old_value='Open',
					new_value='Restricted',
					change_type=ChangeType.ADDED,
					impact=ChangeImpact.RESTRICTIVE,
					description='Purpose limitation rules applied.',
				)
			)
			return

		# Case: Removed Purpose Restrictions (Was restricted, now open) -> Permissive (High Risk)
		if old and not new:
			report.changes.append(
				DiffItem(
					category='Purpose',
					field='rule',
					old_value='Restricted',
					new_value='Open',
					change_type=ChangeType.REMOVED,
					impact=ChangeImpact.PERMISSIVE,
					description='Purpose limitation removed. Data can be used for any purpose.',
				)
			)
			return

		if old and new:
			# 1. Allowed Purposes (Intersection Logic)
			# Adding an allowed purpose expands the intersection -> Permissive
			added_allowed = new.allowed_purposes - old.allowed_purposes
			if added_allowed:
				report.changes.append(
					DiffItem(
						category='Purpose',
						field='allowed_purposes',
						old_value=None,
						new_value=list(added_allowed),
						change_type=ChangeType.MODIFIED,
						impact=ChangeImpact.PERMISSIVE,
						description=f'Allowed purposes expanded: {", ".join(added_allowed)}',
					)
				)

			# Removing an allowed purpose shrinks intersection -> Restrictive
			removed_allowed = old.allowed_purposes - new.allowed_purposes
			if removed_allowed:
				report.changes.append(
					DiffItem(
						category='Purpose',
						field='allowed_purposes',
						old_value=list(removed_allowed),
						new_value=None,
						change_type=ChangeType.MODIFIED,
						impact=ChangeImpact.RESTRICTIVE,
						description=f'Allowed purposes reduced: {", ".join(removed_allowed)}',
					)
				)

			# 2. Denied Purposes (Union Logic)
			# Adding a denied purpose -> Restrictive
			added_denied = new.denied_purposes - old.denied_purposes
			if added_denied:
				report.changes.append(
					DiffItem(
						category='Purpose',
						field='denied_purposes',
						old_value=None,
						new_value=list(added_denied),
						change_type=ChangeType.MODIFIED,
						impact=ChangeImpact.RESTRICTIVE,
						description=f'Denied purposes added: {", ".join(added_denied)}',
					)
				)

			# Removing a denied purpose -> Permissive
			removed_denied = old.denied_purposes - new.denied_purposes
			if removed_denied:
				report.changes.append(
					DiffItem(
						category='Purpose',
						field='denied_purposes',
						old_value=list(removed_denied),
						new_value=None,
						change_type=ChangeType.MODIFIED,
						impact=ChangeImpact.PERMISSIVE,
						description=f'Denied purposes removed: {", ".join(removed_denied)}',
					)
				)

	def _diff_privacy(self, old: EffectivePrivacy | None, new: EffectivePrivacy | None, report: PolicyDiffReport):
		if old == new:
			return

		# Added Privacy Rule -> Restrictive
		if not old and new:
			report.changes.append(
				DiffItem(
					category='Privacy',
					field='rule',
					old_value='None',
					new_value=new.method.name,
					change_type=ChangeType.ADDED,
					impact=ChangeImpact.RESTRICTIVE,
					description=f'Privacy method {new.method.name} applied.',
				)
			)
			return

		# Removed Privacy Rule -> Permissive (High Risk)
		if old and not new:
			report.changes.append(
				DiffItem(
					category='Privacy',
					field='rule',
					old_value=old.method.name,
					new_value='None',
					change_type=ChangeType.REMOVED,
					impact=ChangeImpact.PERMISSIVE,
					description=f'Privacy method {old.method.name} removed. Data is now raw/unmasked.',
				)
			)
			return

		if old and new:
			# 1. Method Hierarchy Check
			# Enum Value: Unspecified(0) < Pseudonymization(1) < Anonymization(2) < Differential Privacy(3)
			if old.method != new.method:
				if new.method.value > old.method.value:
					impact = ChangeImpact.RESTRICTIVE
					desc = 'Privacy method upgraded (stronger protection).'
				else:
					impact = ChangeImpact.PERMISSIVE
					desc = 'Privacy method downgraded (weaker protection).'

				report.changes.append(
					DiffItem(
						category='Privacy',
						field='method',
						old_value=old.method.name,
						new_value=new.method.name,
						change_type=ChangeType.MODIFIED,
						impact=impact,
						description=f'{desc} {old.method.name} -> {new.method.name}.',
					)
				)

			# 2. Parameter Check (Epsilon, K-Anonymity)
			# We assume dictionaries are comparable strings for standard diff,
			# but we apply specific logic for known numeric params.
			if old.parameters != new.parameters:
				# Epsilon Check (Differential Privacy)
				self._diff_numeric_param(
					'epsilon',
					old.parameters,
					new.parameters,
					report,
					lower_is_stricter=True,  # Lower budget = More noise = Stricter
				)

				# K-Anonymity Check
				self._diff_numeric_param(
					'k',
					old.parameters,
					new.parameters,
					report,
					lower_is_stricter=False,  # Higher k = larger groups = Stricter
				)

				# Generic fallback if params changed but not captured above
				if 'epsilon' not in old.parameters and 'k' not in old.parameters:
					# Just mark as neutral metadata change for now
					report.changes.append(
						DiffItem(
							category='Privacy',
							field='parameters',
							old_value=old.parameters,
							new_value=new.parameters,
							change_type=ChangeType.MODIFIED,
							impact=ChangeImpact.NEUTRAL,
							description='Privacy configuration parameters updated.',
						)
					)

	def _diff_numeric_param(
		self,
		key: str,
		old_params: dict[str, Any],
		new_params: dict[str, Any],
		report: PolicyDiffReport,
		lower_is_stricter: bool,
	):
		"""Helper to diff numeric privacy parameters like epsilon or k."""
		if key in old_params and key in new_params:
			try:
				val_old = float(old_params[key])
				val_new = float(new_params[key])

				if val_old == val_new:
					return

				# Determine Impact
				is_stricter = val_new < val_old if lower_is_stricter else val_new > val_old
				impact = ChangeImpact.RESTRICTIVE if is_stricter else ChangeImpact.PERMISSIVE

				report.changes.append(
					DiffItem(
						category='Privacy',
						field=f'parameters.{key}',
						old_value=val_old,
						new_value=val_new,
						change_type=ChangeType.MODIFIED,
						impact=impact,
						description=f'Privacy parameter {key} changed from {val_old} to {val_new}.',
					)
				)
			except ValueError:
				# If values aren't numbers, ignore numeric diff logic
				pass
