"""Minimal checks for PricingService.scrape_competitor_price parsing"""
from unittest.mock import patch, MagicMock
from services.pricing import PricingService

svc = PricingService(None, None, None)

def fake_response(json_data=None, text="", ok=True):
    r = MagicMock()
    r.raise_for_status = lambda: None
    r.json = lambda: json_data
    r.text = text
    return r

# 1. Price from .json endpoint
with patch('services.pricing.requests.get', return_value=fake_response(
        {'product': {'variants': [{'price': '42.50'}]}})):
    assert svc.scrape_competitor_price('X', 'https://example.com/products/foo') == 42.50

# 2. JSON fails -> JSON-LD fallback
with patch('services.pricing.requests.get', side_effect=[
    Exception("404"),
    fake_response(text='<script type="application/ld+json">{"price":"19.99"}</script>')
]):
    assert svc.scrape_competitor_price('X', 'https://example.com/products/foo') == 19.99

# 3. Both fail -> None
with patch('services.pricing.requests.get', side_effect=Exception("404")):
    assert svc.scrape_competitor_price('X', 'https://example.com/products/foo') is None

# 4. Empty URL -> None
assert svc.scrape_competitor_price('X', '') is None

print("All pricing tests passed!")
