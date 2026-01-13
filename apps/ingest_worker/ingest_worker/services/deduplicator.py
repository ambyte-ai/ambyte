import hashlib
import json
import logging
from datetime import timedelta

from ambyte_schemas.models.obligation import (
	EnforcementLevel,
	Obligation,
	ResourceSelector,
	SourceProvenance,
)
from ingest_worker.config import settings
from ingest_worker.schemas.ingest import ExtractedConstraint

logger = logging.getLogger(__name__)


class Deduplicator:
	"""
	PASS 3: The Merge Strategy.

	Aggregates duplicate constraints extracted from different sections of the document.

	Logic:
	1. Group by 'Constraint Logic' (e.g. Retention: 30d).
	2. Group by 'Subject' (e.g. "Customer Data").
	3. Merge Provenance (e.g. "Cited in Section 4.1 AND Section 12.5").
	"""

	def merge(
		self,
		raw_constraints: list[ExtractedConstraint],
		filename: str,
		project_id: str | None,
		s3_key: str | None = None,
	) -> list[Obligation]:
		logger.info('Starting Pass 3: Deduplication and Merging')

		# 1. Hashing & Grouping
		groups: dict[str, list[ExtractedConstraint]] = {}

		for item in raw_constraints:
			key = self._generate_fingerprint(item)

			if key not in groups:
				groups[key] = []
			groups[key].append(item)

		final_obligations = []

		# 2. Consolidation
		for key, items in groups.items():
			items.sort(key=lambda x: 1 if x.mapped_regulation_id else 0, reverse=True)
			# We use the first item as the "Master" for the technical definition
			master = items[0]

			# We aggregate provenance from all items
			combined_rationale, primary_section = self._merge_rationales(items)

			# Generate a stable ID
			stable_slug = f'auto-{key[:12]}'

			# Map the intermediate "ExtractedConstraint" to the final "Obligation"
			obligation = self._convert_to_obligation(
				slug=stable_slug,
				master=master,
				rationale=combined_rationale,
				filename=filename,
				section_ref=primary_section,
				s3_key=s3_key,
			)

			final_obligations.append(obligation)

		logger.info(
			f'Pass 3 Complete. Reduced {len(raw_constraints)} raw items to {len(final_obligations)} obligations.'
		)
		return final_obligations

	def _generate_fingerprint(self, item: ExtractedConstraint) -> str:
		"""
		Creates a deterministic hash of the semantic content.
		Ignores quote/provenance.
		"""
		# We build a dict of the fields that define the "Rule Logic"
		logic_fingerprint = {
			'category': item.category,
			'subject': item.subject.lower().strip(),  # Normalize subject
		}

		# Add the specific rule parameters
		if item.retention_rule:
			logic_fingerprint['retention'] = item.retention_rule.model_dump(mode='json')
		if item.geofencing_rule:
			logic_fingerprint['geofencing'] = item.geofencing_rule.model_dump(mode='json')
		if item.ai_rule:
			logic_fingerprint['ai'] = item.ai_rule.model_dump(mode='json')
		if item.privacy_rule:
			logic_fingerprint['privacy'] = item.privacy_rule.model_dump(mode='json')
		if item.purpose_rule:
			logic_fingerprint['purpose'] = item.purpose_rule.model_dump(mode='json')

		# Sort keys to ensure stable JSON
		serialized = json.dumps(logic_fingerprint, sort_keys=True)
		return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

	def _merge_rationales(self, items: list[ExtractedConstraint]) -> tuple[str, str | None]:
		"""
		Combines rationales with their source context.
		Returns: (Combined String, Primary Section Reference)
		"""
		unique_entries = []
		seen_rationales = set()
		primary_section = None

		for item in items:
			# Format: "[Section 3.1 Security]: Data must be encrypted."
			prefix = ''
			section_ref = None

			if item.source_metadata:
				# Try to find the most specific section header
				hierarchy = item.source_metadata.get('section_hierarchy', [])
				if hierarchy:
					# Use the last item in hierarchy (most specific)
					section_ref = hierarchy[-1]
					prefix = f'[{section_ref}] '

					# Capture the first valid section ref as primary
					if not primary_section:
						primary_section = section_ref

			# Construct the entry
			full_text = f'{prefix}{item.rationale}'

			if full_text not in seen_rationales:
				unique_entries.append(full_text)
				seen_rationales.add(full_text)

		# If we have multiple unique rationales, join them.
		# If single, just return it.
		return ' | '.join(unique_entries), primary_section

	def _resolve_target_tags(self, verbose_subject: str) -> dict[str, str]:
		"""
		Maps verbose legal subjects to canonical engineering tags.
		"""
		s = verbose_subject.lower()

		# 1. PII / Personal Data
		if any(x in s for x in ['personal data', 'pii', 'personally identifiable']):
			# Most data engineers tag this as 'category: pii' or 'sensitivity: high'
			return {'category': 'pii'}

		# 2. Financial / Payment
		if any(x in s for x in ['financial', 'payment', 'cardholder', 'pci']):
			return {'category': 'financial', 'sensitivity': 'restricted'}

		# 3. Health / PHI
		if any(x in s for x in ['health', 'medical', 'phi', 'patient']):
			return {'category': 'health', 'sensitivity': 'restricted'}

		# 4. Usage / Telemetry
		if any(x in s for x in ['usage', 'telemetry', 'logs', 'analytics']):
			return {'category': 'telemetry'}

		# 5. Confidential Information
		if 'confidential' in s:
			return {'sensitivity': 'confidential'}

		# 6. Fallback: Clean Snake Case (Truncated)
		# "Personal Data originating from..." -> "personal_data_originating"
		clean = s.replace('(', '').replace(')', '').replace(',', '')
		slug = '_'.join(clean.split()[:3])  # Take first 3 words only
		return {'category': slug}

	def _convert_to_obligation(
		self,
		slug: str,
		master: ExtractedConstraint,
		rationale: str,
		filename: str,
		section_ref: str | None,
		s3_key: str | None,
	) -> Obligation:
		"""
		Maps the intermediate schema to the official DB schema.
		"""

		# 1. Determine Source ID & Type
		# If mapped, the Source is the Regulation (e.g. "GDPR"), not the uploaded file.
		if master.mapped_regulation_id:
			source_id = master.mapped_regulation_id.split('::')[0]  # e.g. "EU-GDPR..."
			doc_type = 'REGULATION'
			# We append the original filename to rationale so we don't lose the context
			rationale = f'[Found in {filename}] ' + rationale
		else:
			source_id = filename
			doc_type = 'CONTRACT_UPLOAD'

		target_tags = self._resolve_target_tags(master.subject)

		if 'eea' in master.subject.lower() or 'europe' in master.subject.lower():
			target_tags['origin'] = 'eea'

		target = ResourceSelector(match_tags=target_tags)

		# ----------------------------------------------------------------------
		# SAFETY INTERCEPTOR: Prevent Immediate Data Loss (0s Retention)
		# ----------------------------------------------------------------------
		enforcement_level = EnforcementLevel.BLOCKING  # Default

		# Check for the "Poison Pill" scenario
		if master.retention_rule:
			# Check if duration is effectively zero
			is_zero_duration = master.retention_rule.duration.total_seconds() <= 0

			if is_zero_duration:
				# 1. Force a Safe Default Duration (e.g., 365 days) to prevent instant deletion logic
				# even if the trigger is EVENT_DATE, because the SDK might fallback to creation time.
				master.retention_rule.duration = timedelta(days=365)

				# 2. Downgrade to AUDIT_ONLY
				# We cannot block access based on a heuristic guess.
				enforcement_level = EnforcementLevel.AUDIT_ONLY

				# 3. Append explanation to rationale for transparency
				rationale += (
					' [SYSTEM: Duration was 0s (Immediate Deletion). '
					'Auto-corrected to 365d and downgraded to AUDIT_ONLY for safety.]'
				)
		# 3. Construct Obligation
		return Obligation(
			id=slug,
			title=f'{master.category.title()} Rule for {master.subject}',
			description=rationale,
			provenance=SourceProvenance(
				source_id=source_id,
				document_type=doc_type,
				# Use the actual primary section if we found one
				section_reference=section_ref or 'Extracted Section',
				document_uri=f's3://{settings.S3_BUCKET_NAME}/{s3_key}' if s3_key else f's3://uploads/{filename}',
			),
			enforcement_level=enforcement_level,
			target=target,
			# Polymorphic Assignment
			retention=master.retention_rule,
			geofencing=master.geofencing_rule,
			purpose=master.purpose_rule,
			privacy=master.privacy_rule,
			ai_model=master.ai_rule,
		)
