import os
import sys
import time

import httpx
from ambyte_schemas.models.common import SensitivityLevel
from ambyte_schemas.models.obligation import (
	EnforcementLevel,
	GeofencingRule,
	Obligation,
	ResourceSelector,
	SourceProvenance,
)
from dotenv import load_dotenv
from src.schemas.inventory import ResourceCreate

load_dotenv()  # Load from .env if present

# Configuration
API_URL = os.getenv('AMBYTE_API_URL', 'http://localhost:8000/v1')
API_KEY = os.getenv('AMBYTE_API_KEY')

if not API_KEY:
	print('❌ Error: AMBYTE_API_KEY environment variable is not set.')
	print("Run 'docker compose exec api python src/scripts/init_db.py' to generate one.")
	sys.exit(1)

HEADERS = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}

# Test Data
URN_SENSITIVE = 'urn:ambyte:smoke:sensitive-db'
URN_PUBLIC = 'urn:ambyte:smoke:public-logs'


def print_step(msg: str):
	print(f'\n🔹 {msg}')


def assert_status(response, expected_code=200):
	if response.status_code != expected_code:
		print(f'❌ Failed. Expected {expected_code}, got {response.status_code}')
		print(f'Response: {response.text}')
		sys.exit(1)


def step_1_push_inventory(client):
	print_step('Step 1: Sync Inventory (Register Resources)')

	# We register one High Sensitivity resource
	resource = ResourceCreate(
		urn=URN_SENSITIVE,
		platform='snowflake',
		name='Smoke Test Customers',
		attributes={'sensitivity': SensitivityLevel.CONFIDENTIAL, 'tags': {'env': 'prod', 'dept': 'finance'}},
	)

	payload = {'resources': [resource.model_dump(mode='json')]}

	resp = client.put(f'{API_URL}/resources/', json=payload)
	assert_status(resp, 200)

	print(f'✅ Registered {len(resp.json())} resources.')


def step_2_push_policy(client):
	print_step('Step 2: Push Policy (Obligations)')

	# Define a Geofencing Rule: Data tagged "finance" must stay in "EU"
	obligation = Obligation(
		id='smoke-test-geo-eu',
		title='Finance Data EU Residency',
		description='Smoke test rule',
		provenance=SourceProvenance(source_id='SMOKE-TEST', document_type='TEST'),
		enforcement_level=EnforcementLevel.BLOCKING,
		# Target: Match resources with tag dept=finance
		target=ResourceSelector(match_tags={'dept': 'finance'}),
		# Constraint: Only EU allowed
		geofencing=GeofencingRule(allowed_regions=['EU', 'DE', 'FR'], strict_residency=True),
	)

	# Use 'exclude_none' to keep payload clean
	payload = {'obligations': [obligation.model_dump(mode='json', exclude_none=True)]}

	resp = client.put(f'{API_URL}/obligations/', json=payload)
	assert_status(resp, 200)

	print('✅ Policy pushed successfully.')


def step_3_check_allow(client):
	print_step('Step 3: Check Access (Expect ALLOW)')

	# Scenario: Accessing from Germany (Allowed)
	payload = {
		'resource_urn': URN_SENSITIVE,
		'action': 'query',
		'actor_id': 'data_scientist_alice',
		'context': {
			'region': 'DE',  # Matches Allowed List
			'purpose': 'analytics',
		},
	}

	resp = client.post(f'{API_URL}/check/', json=payload)
	assert_status(resp, 200)
	data = resp.json()

	if data['allowed'] is True:
		print(f'✅ Access Allowed as expected. Reason: {data["reason"]}')
	else:
		print(f'❌ Unexpected DENY. Reason: {data["reason"]}')
		sys.exit(1)


def step_4_check_deny(client):
	print_step('Step 4: Check Access (Expect DENY)')

	# Scenario: Accessing from US (Blocked by Geo policy)
	payload = {
		'resource_urn': URN_SENSITIVE,
		'action': 'query',
		'actor_id': 'us_analyst_bob',
		'context': {
			'region': 'US',  # Not in Allowed List
			'purpose': 'analytics',
		},
	}

	resp = client.post(f'{API_URL}/check/', json=payload)
	assert_status(resp, 200)
	data = resp.json()

	if data['allowed'] is False:
		print(f'✅ Access Denied as expected. Reason: {data["reason"]}')
	else:
		print('❌ Unexpected ALLOW. Policy did not enforce geofencing.')
		sys.exit(1)


def step_5_check_caching(client):
	print_step('Step 5: Verify Caching (Performance)')

	payload = {
		'resource_urn': URN_SENSITIVE,
		'action': 'query',
		'actor_id': 'cache_tester',
		'context': {'region': 'US'},
	}

	# First hit (warm up if needed)
	client.post(f'{API_URL}/check/', json=payload)

	# Second hit should be fast and indicate cache usage if API returns headers/metadata
	start = time.time()
	resp = client.post(f'{API_URL}/check/', json=payload)
	duration = (time.time() - start) * 1000

	data = resp.json()
	cache_hit = data.get('cache_hit', False)

	print(f'⏱️  Request took {duration:.2f}ms. Cache Hit: {cache_hit}')

	if duration > 50 and not cache_hit:
		print('⚠️  Warning: Request seems slow or cache miss.')
	else:
		print('✅ Performance looks good.')


def main():
	print(f'🚀 Starting Ambyte Smoke Test against {API_URL}')

	try:
		with httpx.Client(headers=HEADERS, timeout=5.0) as client:
			# 0. Healthcheck
			resp = client.get(API_URL.replace('/v1', '/ping'))
			if resp.status_code != 200:
				print('❌ API is not healthy.')
				sys.exit(1)

			step_1_push_inventory(client)
			step_2_push_policy(client)

			# Give a tiny pause for eventual consistency (if any async writes)
			# though current implementation is transactional for policies.
			time.sleep(0.5)

			step_3_check_allow(client)
			step_4_check_deny(client)
			step_5_check_caching(client)

	except httpx.ConnectError:
		print(f'❌ Could not connect to {API_URL}. Is Docker running?')
		sys.exit(1)
	except Exception as e:
		print(f'❌ unexpected error: {e}')
		sys.exit(1)

	print('\n✨ All Systems Go! Integration test passed.')


if __name__ == '__main__':
	main()
