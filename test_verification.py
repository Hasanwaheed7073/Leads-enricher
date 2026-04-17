"""Quick test to verify the new domain/email/person checks in Agent 2."""

from agent2_scout import WebScout

scout = WebScout()

print("=" * 60)
print("TEST 1: Dead domain (bobshvac.com)")
print("=" * 60)
r = scout.scrape_website("https://bobshvac.com", email="bob@example.com", person_name="Bob")
print(f"  domain_alive:         {r.get('domain_alive')}")
print(f"  has error:            {'error' in r}")
print(f"  error msg:            {r.get('error', 'none')}")
print()

print("=" * 60)
print("TEST 2: Real domain (example.com) with dummy email")
print("=" * 60)
r2 = scout.scrape_website("https://example.com", email="alice@example.com", person_name="Alice")
print(f"  domain_alive:         {r2.get('domain_alive')}")
print(f"  email_domain_matches: {r2.get('email_domain_matches')}")
print(f"  email_found_on_page:  {r2.get('email_found_on_page')}")
print(f"  person_found_on_page: {r2.get('person_found_on_page')}")
print(f"  has error:            {'error' in r2}")
print()

scout.close()
print("All tests complete.")
