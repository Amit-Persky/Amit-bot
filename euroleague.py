import requests
import xml.etree.ElementTree as ET
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

class EuroleagueService:
    def __init__(self):
        self.baseUrlGames = "https://api-live.euroleague.net/v1/games"
        self.baseUrlResults = "https://api-live.euroleague.net/v1/results"
        self.baseUrlSchedules = "https://api-live.euroleague.net/v1/schedules"
        logging.info("EuroleagueService initialized.")

    def parseResultsXml(self, xmlString: str) -> list:
        root = ET.fromstring(xmlString)
        games = []
        for game in root.findall("game"):
            gameData = {child.tag: child.text for child in game}
            dateStr = gameData.get("date", "").strip()
            timeStr = gameData.get("time", "00:00").strip()
            try:
                gameData["datetime_obj"] = datetime.strptime(dateStr + " " + timeStr, "%b %d, %Y %H:%M")
            except Exception as e:
                logging.error(f"Date format error in results: {e}")
                continue
            games.append(gameData)
        games.sort(key=lambda x: x["datetime_obj"])
        return games

    def parseScheduleXml(self, xmlString: str) -> list:
        root = ET.fromstring(xmlString)
        items = []
        for item in root.findall("item"):
            itemData = {child.tag: child.text for child in item}
            dateStr = itemData.get("date", "").strip()
            timeStr = itemData.get("startime", "00:00").strip()
            try:
                itemData["datetime_obj"] = datetime.strptime(dateStr + " " + timeStr, "%b %d, %Y %H:%M")
            except Exception as e:
                logging.error(f"Date format error in schedule: {e}")
                continue
            items.append(itemData)
        items.sort(key=lambda x: x["datetime_obj"])
        return items

    def filterPastGames(self, games: list, teamName: str) -> list:
        teamLower = teamName.lower()
        now = datetime.now()
        return [g for g in games
                if teamLower in ((g.get("hometeam", "").lower() + " " + g.get("awayteam", "").lower()))
                and g.get("played", "").lower() == "true"
                and g["datetime_obj"] <= now]

    def formatLastGame(self, game: dict, teamName: str) -> str:
        dateText = game.get("date", "N/A")
        homeTeam = game.get("hometeam", "N/A")
        awayTeam = game.get("awayteam", "N/A")
        homeScore = game.get("homescore", "N/A")
        awayScore = game.get("awayscore", "N/A")
        return f"Last game for {teamName} on {dateText}:\n{homeTeam} {homeScore} - {awayScore} {awayTeam}"

    def getLastGameResult(self, seasonCode: str, teamName: str) -> str:
        logging.info(f"Fetching last game result for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlResults, params=params, headers=headers)
        if response.status_code != 200:
            return f"Failed to fetch results. Status code: {response.status_code}"
        try:
            games = self.parseResultsXml(response.text)
            pastGames = self.filterPastGames(games, teamName)
            if not pastGames:
                return f"No past played games found for {teamName} in season {seasonCode}."
            lastGame = pastGames[-1]
            return self.formatLastGame(lastGame, teamName)
        except Exception as e:
            logging.error(f"Error processing last game result: {e}")
            return f"Error processing last game result: {str(e)}"

    def extractGameDatetime(self, item: ET.Element):
        dateElem = item.find("date")
        timeElem = item.find("startime")
        if dateElem is None:
            return None
        dateText = dateElem.text
        timeText = timeElem.text if timeElem is not None else "00:00"
        try:
            dt = datetime.strptime(dateText + " " + timeText, "%b %d, %Y %H:%M")
            return dt, item
        except Exception as e:
            logging.error(f"Error parsing game datetime: {e}")
            return None

    def formatNextGame(self, item: ET.Element, teamName: str) -> str:
        game = item.find("game").text if item.find("game") is not None else "N/A"
        gameCode = item.find("gamecode").text if item.find("gamecode") is not None else "N/A"
        dateStr = item.find("date").text if item.find("date") is not None else "N/A"
        startTime = item.find("startime").text if item.find("startime") is not None else "N/A"
        homeTeam = item.find("hometeam").text if item.find("hometeam") is not None else "N/A"
        awayTeam = item.find("awayteam").text if item.find("awayteam") is not None else "N/A"
        return (f"Next game for {teamName}:\nGame: {game}, Code: {gameCode}\n"
                f"Date: {dateStr} at {startTime}\n{homeTeam} vs {awayTeam}")

    def getNextGame(self, seasonCode: str, teamName: str) -> str:
        # Return the next scheduled game for a given team in a season.
        logging.info(f"Fetching next game for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlSchedules, params=params, headers=headers)
        if response.status_code != 200:
            return f"Failed to fetch schedules. Status code: {response.status_code}"
        try:
            root = ET.fromstring(response.text)
            items = root.findall(".//item")
            if not items:
                return f"No schedule items found for season {seasonCode}."
            nextGames = self.filterUpcomingGames(items, teamName)
            if not nextGames:
                return f"No upcoming games found for {teamName} in season {seasonCode}."
            nextGames.sort(key=lambda x: x[0])
            return self.formatNextGame(nextGames[0][1], teamName)
        except Exception as e:
            logging.error(f"Error processing next game: {e}")
            return f"Error processing next game: {str(e)}"

    def getNextGameFormatted(self, seasonCode: str, teamName: str) -> str:
        # Return the next scheduled game for a team, formatted with details.
        logging.info(f"Fetching next game formatted for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlSchedules, params=params, headers=headers)
        if response.status_code != 200:
            return f"Failed to fetch schedules. Status code: {response.status_code}"
        try:
            items = self.parseScheduleXml(response.text)
            if not items:
                return f"No schedule items found for season {seasonCode}."
            nextGames = self.filterUpcomingGamesDict(items, teamName)
            if not nextGames:
                return f"No upcoming games found for {teamName} in season {seasonCode}."
            nextGames.sort(key=lambda x: x[0])
            return self.formatNextGameFormatted(nextGames[0][1], teamName)
        except Exception as e:
            logging.error(f"Error processing next game formatted: {e}")
            return f"Error processing next game: {str(e)}"

    def getSeasonResults(self, seasonCode: str, teamName: str) -> str:
        # Return all games for a team in a season, sorted by date.
        logging.info(f"Fetching season results for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlResults, params=params, headers=headers)
        if response.status_code != 200:
            return f"Failed to fetch results. Status code: {response.status_code}"
        try:
            root = ET.fromstring(response.text)
            gamesList = self.collectTeamGames(root, teamName)
            if not gamesList:
                return f"No games found for {teamName} in season {seasonCode}."
            gamesList.sort(key=lambda x: x[0])
            return "\n".join([line for _, line in gamesList])
        except Exception as e:
            logging.error(f"Error processing season results: {e}")
            return f"Error processing season results: {str(e)}"

    def formatNextGameFormatted(self, item: dict, teamName: str) -> str:
        dateStr = item.get("date", "N/A")
        startTime = item.get("startime", "N/A")
        homeTeam = item.get("hometeam", "N/A")
        awayTeam = item.get("awayteam", "N/A")
        arena = item.get("arenaname", "N/A")
        return (f"Next game for {teamName}:\nArena: {arena}\n"
                f"Date: {dateStr} at {startTime}\n{homeTeam} vs {awayTeam}")

    def filterUpcomingGames(self, items, teamName):
        """Filter and return upcoming games for the given team from XML items."""
        now = datetime.now()
        teamLower = teamName.lower()
        nextGames = []
        for item in items:
            hometeam = item.find("hometeam").text if item.find("hometeam") is not None else ""
            awayteam = item.find("awayteam").text if item.find("awayteam") is not None else ""
            if teamLower not in (hometeam.lower() + " " + awayteam.lower()):
                continue
            result = self.extractGameDatetime(item)
            if result is None:
                continue
            dt, validItem = result
            if dt >= now:
                nextGames.append((dt, validItem))
        return nextGames

    def filterUpcomingGamesDict(self, items, teamName):
        """Filter and return upcoming games for the given team from parsed dict items."""
        now = datetime.now()
        teamLower = teamName.lower()
        nextGames = []
        for item in items:
            if teamLower not in (item.get("hometeam", "").lower() + " " + item.get("awayteam", "").lower()):
                continue
            if "datetime_obj" not in item:
                continue
            dt = item["datetime_obj"]
            if dt >= now:
                nextGames.append((dt, item))
        return nextGames

    def collectTeamGames(self, root, teamName):
        # Collect and return all games for a team from XML root.
        gamesList = []
        teamLower = teamName.lower()
        for game in root.findall(".//game"):
            ht = game.find("hometeam").text if game.find("hometeam") is not None else ""
            at = game.find("awayteam").text if game.find("awayteam") is not None else ""
            if teamLower in (ht.lower() + " " + at.lower()):
                dt, line = self.formatSeasonGame(game)
                gamesList.append((dt, line))
        return gamesList

    def formatSeasonGame(self, game: ET.Element) -> (datetime, str):
        homeTeam = game.find("hometeam").text if game.find("hometeam") is not None else ""
        awayTeam = game.find("awayteam").text if game.find("awayteam") is not None else ""
        dateText = game.find("date").text if game.find("date") is not None else "N/A"
        try:
            dateObj = datetime.strptime(dateText.strip(), "%b %d, %Y")
        except Exception as e:
            logging.error(f"Date parsing error: {e}")
            dateObj = datetime.min
        roundStr = game.find("round").text if game.find("round") is not None else "N/A"
        homeScore = game.find("homescore").text if game.find("homescore") is not None else "N/A"
        awayScore = game.find("awayscore").text if game.find("awayscore") is not None else "N/A"
        resultLine = f"{dateText}: {homeTeam} {homeScore} - {awayScore} {awayTeam} (Round: {roundStr})"
        return dateObj, resultLine

    def getSeasonResults(self, seasonCode: str, teamName: str) -> str:
        logging.info(f"Fetching season results for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlResults, params=params, headers=headers)
        if response.status_code != 200:
            return f"Failed to fetch results. Status code: {response.status_code}"
        try:
            root = ET.fromstring(response.text)
            gamesList = []
            teamLower = teamName.lower()
            for game in root.findall(".//game"):
                ht = game.find("hometeam").text if game.find("hometeam") is not None else ""
                at = game.find("awayteam").text if game.find("awayteam") is not None else ""
                if teamLower in (ht.lower() + " " + at.lower()):
                    dt, line = self.formatSeasonGame(game)
                    gamesList.append((dt, line))
            if not gamesList:
                return f"No games found for {teamName} in season {seasonCode}."
            gamesList.sort(key=lambda x: x[0])
            return "\n".join([line for _, line in gamesList])
        except Exception as e:
            logging.error(f"Error processing season results: {e}")
            return f"Error processing season results: {str(e)}"

    def formatResults(self, gameResults: ET.Element) -> str:
        roundStr = gameResults.find("round").text if gameResults.find("round") is not None else ""
        gameDay = gameResults.find("gameday").text if gameResults.find("gameday") is not None else ""
        date = gameResults.find("date").text if gameResults.find("date") is not None else ""
        time_ = gameResults.find("time").text if gameResults.find("time") is not None else ""
        homeTeam = gameResults.find("homeTeam").text if gameResults.find("homeTeam") is not None else ""
        homeScore = gameResults.find("homescore").text if gameResults.find("homescore") is not None else ""
        awayTeam = gameResults.find("awayTeam").text if gameResults.find("awayTeam") is not None else ""
        awayScore = gameResults.find("awayscore").text if gameResults.find("awayscore") is not None else ""
        return (f"Results:\nRound: {roundStr}\nGame Day: {gameDay}\nDate: {date}\nTime: {time_}\n"
                f"{homeTeam} {homeScore} - {awayScore} {awayTeam}")

    def getResults(self, seasonCode: str, gameNumber: int) -> str:
        logging.info(f"Fetching results for season: {seasonCode}, game number: {gameNumber}")
        params = {"seasonCode": seasonCode, "gameNumber": gameNumber}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlResults, params=params, headers=headers)
        if response.status_code != 200:
            return f"Failed to retrieve results. Status code: {response.status_code}"
        try:
            root = ET.fromstring(response.text)
            gameResults = root.find(".//gameResults")
            if gameResults is not None:
                result = self.formatResults(gameResults)
                logging.info("Results parsed successfully.")
                return result
            else:
                logging.error("No game results found in XML.")
                return "No game results found."
        except Exception as e:
            logging.error(f"Error parsing results: {e}")
            return f"Error parsing results: {str(e)}"

    def formatScheduleItem(self, item: ET.Element) -> str:
        game = item.find("game")
        gamecode = item.find("gamecode")
        date = item.find("date")
        startTime = item.find("startime")
        homeTeam = item.find("hometeam")
        awayTeam = item.find("awayteam")
        return (f"Game: {game.text if game is not None else 'N/A'}, "
                f"Code: {gamecode.text if gamecode is not None else 'N/A'}, "
                f"Date: {date.text if date is not None else 'N/A'}, "
                f"Start Time: {startTime.text if startTime is not None else 'N/A'}, "
                f"{homeTeam.text if homeTeam is not None else 'N/A'} vs "
                f"{awayTeam.text if awayTeam is not None else 'N/A'}")

    def getSchedules(self, seasonCode: str, gameNumber: int, teamName: str) -> str:
        logging.info(f"Fetching schedules for season: {seasonCode}, game number: {gameNumber}, team: {teamName}")
        params = {"seasonCode": seasonCode, "gameNumber": gameNumber}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlSchedules, params=params, headers=headers)
        if response.status_code != 200:
            return f"Failed to retrieve schedules. Status code: {response.status_code}"
        try:
            root = ET.fromstring(response.text)
            items = root.findall(".//item")
            if items:
                results = [self.formatScheduleItem(item) for item in items]
                logging.info("Schedules parsed successfully.")
                return "\n".join(results)
            else:
                logging.info("No schedule items found.")
                return "No schedule items found."
        except Exception as e:
            logging.error(f"Error parsing schedule response: {e}")
            return f"Error parsing schedule response: {str(e)}"
