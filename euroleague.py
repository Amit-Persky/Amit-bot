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

    def parse_results_xml(self, xml_string: str) -> list:
        """
        Parses the XML returned from the 'results' endpoint.
        The expected root is <results> containing multiple <game> elements.
        """
        root = ET.fromstring(xml_string)
        games = []
        for game in root.findall("game"):
            game_data = {child.tag: child.text for child in game}
            # Attempt to construct a full datetime if start time is present (not always).
            date_str = game_data.get("date", "").strip()
            time_str = game_data.get("time", "00:00").strip()
            try:
                game_data["datetime_obj"] = datetime.strptime(date_str + " " + time_str, "%b %d, %Y %H:%M")
            except Exception as e:
                logging.error(f"Date format error in results: {e}")
                continue
            games.append(game_data)
        games.sort(key=lambda x: x["datetime_obj"])
        return games

    def parse_schedule_xml(self, xml_string: str) -> list:
        """
        Parses the XML returned from the 'schedules' endpoint.
        The expected root is <schedule> containing multiple <item> elements.
        """
        root = ET.fromstring(xml_string)
        items = []
        for item in root.findall("item"):
            item_data = {child.tag: child.text for child in item}
            date_str = item_data.get("date", "").strip()
            time_str = item_data.get("startime", "00:00").strip()
            try:
                item_data["datetime_obj"] = datetime.strptime(date_str + " " + time_str, "%b %d, %Y %H:%M")
            except Exception as e:
                logging.error(f"Date format error in schedule: {e}")
                continue
            items.append(item_data)
        items.sort(key=lambda x: x["datetime_obj"])
        return items

    def getLastGameResult(self, seasonCode: str, teamName: str) -> str:
        logging.info(f"Fetching last game result for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        # Using the 'results' endpoint to fetch past games
        response = requests.get(self.baseUrlResults, params=params, headers=headers)
        if response.status_code == 200:
            try:
                games = self.parse_results_xml(response.text)
                team_lower = teamName.lower()
                past_games = [
                    g for g in games
                    if team_lower in (g.get("hometeam", "").lower() + " " + g.get("awayteam", "").lower())
                    and g.get("played", "").lower() == "true"
                    and g["datetime_obj"] <= datetime.now()
                ]
                if not past_games:
                    return f"No past played games found for {teamName} in season {seasonCode}."
                last_game = past_games[-1]
                date_text = last_game.get("date", "N/A")
                homeTeam = last_game.get("hometeam", "N/A")
                awayTeam = last_game.get("awayteam", "N/A")
                homeScore = last_game.get("homescore", "N/A")
                awayScore = last_game.get("awayscore", "N/A")
                result = f"Last game for {teamName} on {date_text}:\n{homeTeam} {homeScore} - {awayScore} {awayTeam}"
                return result
            except Exception as e:
                logging.error(f"Error processing last game result: {e}")
                return f"Error processing last game result: {str(e)}"
        else:
            return f"Failed to fetch results. Status code: {response.status_code}"

    def getNextGame(self, seasonCode: str, teamName: str) -> str:
        """
        Returns basic information about the next game (without detailed formatting).
        """
        logging.info(f"Fetching next game for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlSchedules, params=params, headers=headers)
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                items = root.findall(".//item")
                if not items:
                    return f"No schedule items found for season {seasonCode}."
                now = datetime.now()
                team_lower = teamName.lower()
                next_games = []
                for item in items:
                    home_team = item.find("hometeam").text if item.find("hometeam") is not None else ""
                    away_team = item.find("awayteam").text if item.find("awayteam") is not None else ""
                    if team_lower not in (home_team.lower() + " " + away_team.lower()):
                        continue
                    date_text = item.find("date").text if item.find("date") is not None else None
                    start_time_text = item.find("startime").text if item.find("startime") is not None else "00:00"
                    if date_text is None:
                        continue
                    try:
                        game_datetime = datetime.strptime(date_text + " " + start_time_text, "%b %d, %Y %H:%M")
                    except Exception as e:
                        logging.error(f"Error parsing game datetime: {e}")
                        continue
                    if game_datetime >= now:
                        next_games.append((game_datetime, item))
                if not next_games:
                    return f"No upcoming games found for {teamName} in season {seasonCode}."
                next_games.sort(key=lambda x: x[0])
                next_game = next_games[0][1]
                game = next_game.find("game").text if next_game.find("game") is not None else "N/A"
                gamecode = next_game.find("gamecode").text if next_game.find("gamecode") is not None else "N/A"
                date_str = next_game.find("date").text if next_game.find("date") is not None else "N/A"
                start_time = next_game.find("startime").text if next_game.find("startime") is not None else "N/A"
                home_team = next_game.find("hometeam").text if next_game.find("hometeam") is not None else "N/A"
                away_team = next_game.find("awayteam").text if next_game.find("awayteam") is not None else "N/A"
                result = (f"Next game for {teamName}:\n"
                          f"Game: {game}, Code: {gamecode}\n"
                          f"Date: {date_str} at {start_time}\n"
                          f"{home_team} vs {away_team}")
                return result
            except Exception as e:
                logging.error(f"Error processing next game: {e}")
                return f"Error processing next game: {str(e)}"
        else:
            return f"Failed to fetch schedules. Status code: {response.status_code}"

    def getNextGameFormatted(self, seasonCode: str, teamName: str) -> str:
        """
        Returns the next game with more detailed formatting (including arena name).
        Uses parse_schedule_xml() to process the data.
        """
        logging.info(f"Fetching next game formatted for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlSchedules, params=params, headers=headers)
        if response.status_code == 200:
            try:
                items = self.parse_schedule_xml(response.text)
                if not items:
                    return f"No schedule items found for season {seasonCode}."
                now = datetime.now()
                team_lower = teamName.lower()
                next_games = []
                for item in items:
                    if team_lower not in (item.get("hometeam", "").lower() + " " + item.get("awayteam", "").lower()):
                        continue
                    if "datetime_obj" not in item:
                        continue
                    game_datetime = item["datetime_obj"]
                    if game_datetime >= now:
                        next_games.append((game_datetime, item))
                if not next_games:
                    return f"No upcoming games found for {teamName} in season {seasonCode}."
                next_games.sort(key=lambda x: x[0])
                next_game = next_games[0][1]
                date_str = next_game.get("date", "N/A")
                start_time = next_game.get("startime", "N/A")
                home_team = next_game.get("hometeam", "N/A")
                away_team = next_game.get("awayteam", "N/A")
                arena = next_game.get("arenaname", "N/A")
                result = (f"Next game for {teamName}:\n"
                          f"Arena: {arena}\n"
                          f"Date: {date_str} at {start_time}\n"
                          f"{home_team} vs {away_team}")
                return result
            except Exception as e:
                logging.error(f"Error processing next game formatted: {e}")
                return f"Error processing next game: {str(e)}"
        else:
            return f"Failed to fetch schedules. Status code: {response.status_code}"

    def getSeasonResults(self, seasonCode: str, teamName: str) -> str:
        logging.info(f"Fetching season results for team: {teamName} in season: {seasonCode}")
        params = {"seasonCode": seasonCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlResults, params=params, headers=headers)
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                games_list = []
                team_lower = teamName.lower()
                for game in root.findall(".//game"):
                    homeTeam = game.find("hometeam").text if game.find("hometeam") is not None else ""
                    awayTeam = game.find("awayteam").text if game.find("awayteam") is not None else ""
                    if team_lower in (homeTeam.lower() + " " + awayTeam.lower()):
                        date_text = game.find("date").text if game.find("date") is not None else "N/A"
                        try:
                            date_obj = datetime.strptime(date_text.strip(), "%b %d, %Y")
                        except Exception as e:
                            logging.error(f"Date parsing error: {e}")
                            date_obj = datetime.min
                        roundStr = game.find("round").text if game.find("round") is not None else "N/A"
                        homeScore = game.find("homescore").text if game.find("homescore") is not None else "N/A"
                        awayScore = game.find("awayscore").text if game.find("awayscore") is not None else "N/A"
                        result_line = (
                            f"{date_text}: {homeTeam} {homeScore} - {awayScore} {awayTeam} (Round: {roundStr})"
                        )
                        games_list.append((date_obj, result_line))
                if not games_list:
                    return f"No games found for {teamName} in season {seasonCode}."
                games_list.sort(key=lambda x: x[0])
                final_results = "\n".join([line for _, line in games_list])
                return final_results
            except Exception as e:
                logging.error(f"Error processing season results: {e}")
                return f"Error processing season results: {str(e)}"
        else:
            return f"Failed to fetch results. Status code: {response.status_code}"

    def getGameResults(self, seasonCode: str, gameCode: int, teamName: str) -> str:
        logging.info(f"Fetching game results for season: {seasonCode}, game code: {gameCode}, team: {teamName}")
        params = {"seasonCode": seasonCode, "gamecode": gameCode}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlGames, params=params, headers=headers)
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                localClub = root.find(".//localClub")
                roadClub = root.find(".//roadClub")
                if localClub is not None and roadClub is not None:
                    localScore = localClub.get("score")
                    roadScore = roadClub.get("score")
                    localName = localClub.get("name")
                    roadName = roadClub.get("name")
                    result = f"Game Result: {localName} {localScore} - {roadScore} {roadName}"
                    logging.info("Game results parsed successfully.")
                    return result
                else:
                    logging.error("Could not parse game results from XML.")
                    return "Could not parse game results."
            except Exception as e:
                logging.error(f"Error parsing game results: {e}")
                return f"Error parsing response: {str(e)}"
        else:
            logging.error(f"Failed to retrieve game results. Status code: {response.status_code}")
            return f"Failed to retrieve game results. Status code: {response.status_code}"

    def getResults(self, seasonCode: str, gameNumber: int) -> str:
        logging.info(f"Fetching results for season: {seasonCode}, game number: {gameNumber}")
        params = {"seasonCode": seasonCode, "gameNumber": gameNumber}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlResults, params=params, headers=headers)
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                gameResults = root.find(".//gameResults")
                if gameResults is not None:
                    roundStr = gameResults.find("round").text if gameResults.find("round") is not None else ""
                    gameDay = gameResults.find("gameday").text if gameResults.find("gameday") is not None else ""
                    date = gameResults.find("date").text if gameResults.find("date") is not None else ""
                    time_ = gameResults.find("time").text if gameResults.find("time") is not None else ""
                    homeTeam = gameResults.find("homeTeam").text if gameResults.find("homeTeam") is not None else ""
                    homeScore = gameResults.find("homescore").text if gameResults.find("homescore") is not None else ""
                    awayTeam = gameResults.find("awayTeam").text if gameResults.find("awayTeam") is not None else ""
                    awayScore = gameResults.find("awayscore").text if gameResults.find("awayscore") is not None else ""
                    result = (
                        f"Results:\nRound: {roundStr}\nGame Day: {gameDay}\nDate: {date}\nTime: {time_}\n"
                        f"{homeTeam} {homeScore} - {awayScore} {awayTeam}"
                    )
                    logging.info("Results parsed successfully.")
                    return result
                else:
                    logging.error("No game results found in XML.")
                    return "No game results found."
            except Exception as e:
                logging.error(f"Error parsing results: {e}")
                return f"Error parsing results: {str(e)}"
        else:
            logging.error(f"Failed to retrieve results. Status code: {response.status_code}")
            return f"Failed to retrieve results. Status code: {response.status_code}"

    def getSchedules(self, seasonCode: str, gameNumber: int, teamName: str) -> str:
        logging.info(f"Fetching schedules for season: {seasonCode}, game number: {gameNumber}, team: {teamName}")
        params = {"seasonCode": seasonCode, "gameNumber": gameNumber}
        headers = {"accept": "application/xml"}
        response = requests.get(self.baseUrlSchedules, params=params, headers=headers)
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                items = root.findall(".//item")
                if items:
                    results = []
                    for item in items:
                        game = item.find("game")
                        gamecode = item.find("gamecode")
                        date = item.find("date")
                        startTime = item.find("startime")
                        homeTeam = item.find("hometeam")
                        awayTeam = item.find("awayteam")
                        resultStr = (
                            f"Game: {game.text if game is not None else 'N/A'}, "
                            f"Code: {gamecode.text if gamecode is not None else 'N/A'}, "
                            f"Date: {date.text if date is not None else 'N/A'}, "
                            f"Start Time: {startTime.text if startTime is not None else 'N/A'}, "
                            f"{homeTeam.text if homeTeam is not None else 'N/A'} vs "
                            f"{awayTeam.text if awayTeam is not None else 'N/A'}"
                        )
                        results.append(resultStr)
                    logging.info("Schedules parsed successfully.")
                    return "\n".join(results)
                else:
                    logging.info("No schedule items found.")
                    return "No schedule items found."
            except Exception as e:
                logging.error(f"Error parsing schedule response: {e}")
                return f"Error parsing schedule response: {str(e)}"
        else:
            logging.error(f"Failed to retrieve schedules. Status code: {response.status_code}")
            return f"Failed to retrieve schedules. Status code: {response.status_code}"
