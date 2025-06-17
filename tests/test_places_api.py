import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from unittest.mock import patch, MagicMock
from places_api import PlacesApiService

def mockResponse(json_data=None, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json = MagicMock(return_value=json_data)
    return mock

def testInitLogs():
    with patch('logging.info') as log:
        PlacesApiService('dummy-key')
        log.assert_called()

def testGetPlacesSuccess(monkeypatch):
    service = PlacesApiService('dummy-key')
    mock_places = [{
        'name': 'Place One',
        'formatted_address': '123 Main St',
        'rating': 4.5
    }, {
        'name': 'Place Two',
        'formatted_address': '456 Side St',
        'rating': 4.0
    }]
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({'results': mock_places}, 200))
    s = service.getPlaces('cafe', 'Tel Aviv', limit=2)
    assert 'Here are some recommended cafes in Tel Aviv' in s
    assert 'Place One' in s and 'Place Two' in s
    assert '(Rating: 4.5)' in s

def testGetPlacesNoResults(monkeypatch):
    service = PlacesApiService('dummy-key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({'results': []}, 200))
    s = service.getPlaces('cafe', 'Tel Aviv')
    assert s.startswith("Sorry, I couldn't find any cafe in Tel Aviv.")

def testGetPlacesApiFail(monkeypatch):
    service = PlacesApiService('dummy-key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({}, 500))
    s = service.getPlaces('cafe', 'Tel Aviv')
    assert s.startswith("I'm sorry, I couldn't retrieve places at the moment.")

def testGetPlacesPartialData(monkeypatch):
    service = PlacesApiService('dummy-key')
    mock_places = [{
        # Missing 'name' and 'rating'
        'formatted_address': '789 Unknown Rd'
    }]
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({'results': mock_places}, 200))
    s = service.getPlaces('museum', 'Jerusalem', limit=1)
    assert 'Unnamed Place' in s
    assert 'No address' not in s  # Address is present
    assert '(Rating: N/A)' in s
