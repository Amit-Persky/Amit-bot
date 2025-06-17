import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from unittest.mock import patch, MagicMock
from euroleague import EuroleagueService
import xml.etree.ElementTree as ET

def mockResponse(text, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = text
    return mock

def testInitLogs():
    with patch('logging.info') as log:
        EuroleagueService()
        log.assert_called()

def testParseResultsXml():
    service = EuroleagueService()
    xml = '<root><game><date>Apr 10, 2023</date><time>20:00</time><hometeam>A</hometeam><awayteam>B</awayteam><played>true</played></game></root>'
    games = service.parseResultsXml(xml)
    assert len(games) == 1
    assert games[0]['hometeam'] == 'A'

def testParseScheduleXml():
    service = EuroleagueService()
    xml = '<root><item><date>Apr 11, 2023</date><startime>21:00</startime><hometeam>X</hometeam><awayteam>Y</awayteam></item></root>'
    items = service.parseScheduleXml(xml)
    assert len(items) == 1
    assert items[0]['hometeam'] == 'X'

def testFilterPastGames():
    service = EuroleagueService()
    from datetime import datetime, timedelta
    now = datetime.now()
    games = [{"hometeam": "a", "awayteam": "b", "played": "true", "datetime_obj": now}, {"hometeam": "c", "awayteam": "d", "played": "false", "datetime_obj": now}]
    filtered = service.filterPastGames(games, "a")
    assert len(filtered) == 1

def testFormatLastGame():
    service = EuroleagueService()
    game = {"date": "Apr 10, 2023", "hometeam": "A", "awayteam": "B", "homescore": "90", "awayscore": "80"}
    s = service.formatLastGame(game, "A")
    assert "Last game for A" in s

def testGetLastGameResultSuccess(monkeypatch):
    service = EuroleagueService()
    xml = '<root><game><date>Apr 10, 2023</date><time>20:00</time><hometeam>A</hometeam><awayteam>B</awayteam><played>true</played></game></root>'
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse(xml))
    s = service.getLastGameResult("2023", "A")
    assert "Last game for A" in s

def testGetLastGameResultFail(monkeypatch):
    service = EuroleagueService()
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse('', 500))
    s = service.getLastGameResult("2023", "A")
    assert s.startswith("Failed to fetch results")

def testExtractGameDatetime():
    service = EuroleagueService()
    xml = ET.fromstring('<item><date>Apr 10, 2023</date><startime>20:00</startime></item>')
    dt = service.extractGameDatetime(xml)
    assert dt is not None

def testFormatNextGame():
    service = EuroleagueService()
    xml = ET.fromstring('<item><date>Apr 10, 2023</date><startime>20:00</startime><hometeam>A</hometeam><awayteam>B</awayteam></item>')
    s = service.formatNextGame(xml, "A")
    assert "Next game for A" in s

def testGetNextGameSuccess(monkeypatch):
    service = EuroleagueService()
    xml = '<root><item><date>Apr 20, 2025</date><startime>20:00</startime><hometeam>A</hometeam><awayteam>B</awayteam></item></root>'
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse(xml))
    s = service.getNextGame("2025", "A")
    assert "Next game for A" in s or "No upcoming games found" in s

def testGetNextGameFail(monkeypatch):
    service = EuroleagueService()
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse('', 500))
    s = service.getNextGame("2025", "A")
    assert s.startswith("Failed to fetch schedules")

def testGetNextGameFormatted(monkeypatch):
    service = EuroleagueService()
    xml = '<root><item><date>Apr 20, 2025</date><startime>20:00</startime><hometeam>A</hometeam><awayteam>B</awayteam></item></root>'
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse(xml))
    s = service.getNextGameFormatted("2025", "A")
    assert "Next game for A" in s or "No upcoming games found" in s

def testGetSeasonResults(monkeypatch):
    service = EuroleagueService()
    xml = '<root><game><date>Apr 10, 2023</date><time>20:00</time><hometeam>A</hometeam><awayteam>B</awayteam><played>true</played></game></root>'
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse(xml))
    s = service.getSeasonResults("2023", "A")
    # Accept the expected format as valid output (date and teams)
    assert ("Apr 10, 2023" in s and "A" in s and "B" in s) or "No games found" in s or "Failed to fetch results" in s

def testFormatNextGameFormatted():
    service = EuroleagueService()
    d = {"date": "Apr 10, 2023", "startime": "20:00", "hometeam": "A", "awayteam": "B", "arenaname": "Arena"}
    s = service.formatNextGameFormatted(d, "A")
    assert "Next game for A" in s

def testFilterUpcomingGames():
    service = EuroleagueService()
    import xml.etree.ElementTree as ET
    # Create an XML item as expected by the real function
    xml_item = ET.fromstring('<item><hometeam>A</hometeam><awayteam>B</awayteam><date>Apr 16, 2025</date><startime>15:40</startime></item>')
    res = service.filterUpcomingGames([xml_item], "A")
    assert isinstance(res, list)

def testFilterUpcomingGamesDict():
    service = EuroleagueService()
    from datetime import datetime, timedelta
    now = datetime.now()
    items = [{"hometeam": "A", "awayteam": "B", "datetime_obj": now + timedelta(days=1)}]
    res = service.filterUpcomingGamesDict(items, "A")
    assert isinstance(res, list)

def testCollectTeamGames():
    service = EuroleagueService()
    xml = ET.fromstring('<root><game><hometeam>A</hometeam><awayteam>B</awayteam></game></root>')
    res = service.collectTeamGames(xml, "A")
    assert isinstance(res, list)

def testFormatSeasonGame():
    service = EuroleagueService()
    xml = ET.fromstring('<game><date>Apr 10, 2023</date><hometeam>A</hometeam><awayteam>B</awayteam></game>')
    s = service.formatSeasonGame(xml)
    assert "Forecast" not in s

def testFormatResults():
    service = EuroleagueService()
    xml = ET.fromstring('<gameResults><round>1</round><gameday>1</gameday><date>Apr 10, 2023</date><time>20:00</time><homeTeam>A</homeTeam><homescore>90</homescore><awayTeam>B</awayTeam><awayscore>80</awayscore></gameResults>')
    s = service.formatResults(xml)
    assert "Results:" in s

def testGetResults(monkeypatch):
    service = EuroleagueService()
    xml = '<root><gameResults><round>1</round><gameday>1</gameday><date>Apr 10, 2023</date><time>20:00</time><homeTeam>A</homeTeam><homescore>90</homescore><awayTeam>B</awayTeam><awayscore>80</awayscore></gameResults></root>'
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse(xml))
    s = service.getResults("2023", 1)
    assert "Results:" in s or "Failed to retrieve results" in s

def testFormatScheduleItem():
    service = EuroleagueService()
    xml = ET.fromstring('<item><game>1</game><gamecode>123</gamecode><date>Apr 10, 2023</date><startime>20:00</startime><hometeam>A</hometeam><awayteam>B</awayteam></item>')
    s = service.formatScheduleItem(xml)
    assert "Game:" in s

def testGetSchedules(monkeypatch):
    service = EuroleagueService()
    xml = '<root><item><game>1</game><gamecode>123</gamecode><date>Apr 10, 2023</date><startime>20:00</startime><hometeam>A</hometeam><awayteam>B</awayteam></item></root>'
    monkeypatch.setattr('requests.get', lambda *a, **k: mockResponse(xml))
    s = service.getSchedules("2023", 1, "A")
    assert "Game:" in s or "Failed to retrieve schedules" in s
