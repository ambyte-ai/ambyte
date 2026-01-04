import hashlib
import json
import logging

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
			# We use the first item as the "Master" for the technical definition
			master = items[0]

			# We aggregate provenance from all items
			combined_rationale, primary_section = self._merge_rationales(items)

			# Generate a stable ID
			# Ideally derived from project + filename + rule hash
			# We use the hash we generated earlier
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

		# 1. Target Resolution
		normalized_subject = master.subject.lower().replace(' ', '_')
		target = ResourceSelector(match_tags={'data_category': normalized_subject})

		# 2. Construct
		return Obligation(
			id=slug,
			title=f'{master.category.title()} Rule for {master.subject}',
			description=rationale,
			provenance=SourceProvenance(
				source_id=filename,
				document_type='CONTRACT_UPLOAD',
				# Use the actual primary section if we found one
				section_reference=section_ref or 'Extracted Section',
				document_uri=f's3://{settings.S3_BUCKET_NAME}/{s3_key}' if s3_key else f's3://uploads/{filename}',
			),
			enforcement_level=EnforcementLevel.BLOCKING,  # Default to strict
			target=target,
			# Polymorphic Assignment
			retention=master.retention_rule,
			geofencing=master.geofencing_rule,
			purpose=master.purpose_rule,
			privacy=master.privacy_rule,
			ai_model=master.ai_rule,
		)
