from typing import Optional

from ambyte_rules.models import EffectiveAiRules, EffectiveGeofencing, EffectiveRetention, ResolvedPolicy

from apps.policy_compiler.diff_engine.models import ChangeImpact, ChangeType, DiffItem, PolicyDiffReport


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

		return report

	def _diff_retention(
		self, old: Optional[EffectiveRetention], new: Optional[EffectiveRetention], report: PolicyDiffReport
	):
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
		self, old: Optional[EffectiveGeofencing], new: Optional[EffectiveGeofencing], report: PolicyDiffReport
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

	def _diff_ai(self, old: Optional[EffectiveAiRules], new: Optional[EffectiveAiRules], report: PolicyDiffReport):
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
