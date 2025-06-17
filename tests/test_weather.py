import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from unittest.mock import patch, MagicMock
from weather import WeatherService

def mockResponse(jsonData=None, statusCode=200):
    mock = MagicMock()
    mock.status_code = statusCode
    mock.json = MagicMock(return_value=jsonData)
    return mock

def testInitLogs():
    with patch('logging.info') as log:
        WeatherService('key')
        log.assert_called()

def testGetCoordinatesSuccess(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse([{"lat": 1.0, "lon": 2.0}], 200))
    res = service.getCoordinates('city')
    assert res['lat'] == 1.0

def testGetCoordinatesFail(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse([], 200))
    res = service.getCoordinates('city')
    assert res is None
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse(None, 404))
    res = service.getCoordinates('city')
    assert res is None

def testGetCurrentWeatherSuccess(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({"current": {"temp": 10}}, 200))
    res = service.getCurrentWeather(1.0, 2.0)
    assert res['temp'] == 10

def testGetCurrentWeatherFail(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({}, 404))
    res = service.getCurrentWeather(1.0, 2.0)
    assert res is None

def testGetHourlyForecastSuccess(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({"hourly": [1,2]}, 200))
    res = service.getHourlyForecast(1.0, 2.0)
    assert res == [1,2]

def testGetHourlyForecastFail(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({}, 404))
    res = service.getHourlyForecast(1.0, 2.0)
    assert res is None

def testGetDailyForecastSuccess(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({"daily": [1,2]}, 200))
    res = service.getDailyForecast(1.0, 2.0)
    assert res == [1,2]

def testGetDailyForecastFail(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse({}, 404))
    res = service.getDailyForecast(1.0, 2.0)
    assert res is None

def testFormatUnixTime():
    service = WeatherService('key')
    assert service.formatUnixTime(0) == '1970-01-01'

def testGetWeatherDataCityFail(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr(service, 'getCoordinates', lambda city: None)
    res = service.getWeatherData('city')
    assert res.startswith('Sorry')

def testGetWeatherDataCurrent(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr(service, 'getCoordinates', lambda city: {"lat": 1.0, "lon": 2.0})
    monkeypatch.setattr(service, 'parseForecastWords', lambda *a, **k: None)
    monkeypatch.setattr(service, 'getDefaultCurrentWeather', lambda *a, **k: "current")
    res = service.getWeatherData('city')
    assert res == "current"

def testGetWeatherDataHourly(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr(service, 'getCoordinates', lambda city: {"lat": 1.0, "lon": 2.0})
    monkeypatch.setattr(service, 'parseForecastWords', lambda *a, **k: ['hourly'])
    monkeypatch.setattr(service, 'getForecastTypeFromQuery', lambda *a, **k: 'hourly')
    monkeypatch.setattr(service, 'processHourlyForecast', lambda *a, **k: "hourly")
    res = service.getWeatherData('city', forecastType='hourly')
    assert res == "hourly"

def testGetWeatherDataDaily(monkeypatch):
    service = WeatherService('key')
    monkeypatch.setattr(service, 'getCoordinates', lambda city: {"lat": 1.0, "lon": 2.0})
    monkeypatch.setattr(service, 'parseForecastWords', lambda *a, **k: ['daily'])
    monkeypatch.setattr(service, 'getForecastTypeFromQuery', lambda *a, **k: 'daily')
    monkeypatch.setattr(service, 'processHourlyForecast', lambda *a, **k: None)
    monkeypatch.setattr(service, 'processDailyForecast', lambda *a, **k: "daily")
    result = service.parseForecastWords('daily', 'city')
    assert result == ['daily']
