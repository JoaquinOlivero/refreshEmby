#!/usr/bin/env python3
# Emby Rclone Radarr Sonarr Post-Processing Refresh Script
import requests
import os
import time
import logging
import configparser

dir_path = os.path.dirname(os.path.realpath(__file__))

## Get config.ini values
config = configparser.ConfigParser()
config.read('config.ini')
embyApiKey = config.get("SETTINGS","embyApiKey")
adminId = config.get("SETTINGS","adminId")

def main():

    itemFile = []

    # Radarr env variables
    radarrFileName = os.environ.get('radarr_moviefile_relativepath')
    movieTitle = os.environ.get('radarr_movie_title')
    movieImdbId = os.environ.get('radarr_movie_imdbid')

    # Sonarr env variables
    sonarrFileName = os.environ.get('sonarr_episodefile_relativepath')
    sonarrSeriesTitles = os.environ.get('sonarr_series_title')
    sonarSeriesImdbId = os.environ.get('sonarr_series_imdbid')
    sonarrEpisodeTitle = os.environ.get('sonarr_episodefile_episodetitles') # 'sonarr_episodefile_episodetitles' to 'Last Day'
    sonarrEpisodeSeasonNumber = os.environ.get('sonarr_episodefile_seasonnumber') # 'sonarr_episodefile_seasonnumber' to '1'
    sonarrEpisodeNumber = os.environ.get('sonarr_episodefile_episodenumbers') # Number of episodes in the file

    
    def embyRequest(imdbId):

        def libraryRefreshRequest(imdbId):

            ## Check that Emby is not running a library scan.
            r = requests.get('https://palmtree.com.ar/ScheduledTasks?api_key=' + embyApiKey)
            tasks = r.json()

            for index in range(len(tasks)):
                if "Name" in tasks[index] and tasks[index]["Name"] == "Scan media library" and tasks[index]["State"] != "Idle":
                    logging.info("Emby Is Running a Library Scan. Will retry in 30 seconds")
                    time.sleep(30)
                    libraryRefreshRequest(imdbId)
                    return None

            ## Send library refresh request to emby server
            logging.info('Library refresh request sent')
            requests.post('https://palmtree.com.ar/Library/Refresh/?api_key=' + embyApiKey)
            time.sleep(5)
            embyRequest(imdbId)

        r = requests.get('https://palmtree.com.ar/emby/Users/' + adminId + '/Items?HasImdbId=true&Recursive=True&AnyProviderIdEquals=imdb.'+ imdbId + '&api_key=' + embyApiKey)
        totalItemsFound = r.json()["TotalRecordCount"]
        

        if totalItemsFound == 0:
            logging.info('No items found. Refreshing library in 30s')
            time.sleep(30)
            libraryRefreshRequest(imdbId)
        elif "Type" in r.json()["Items"][0] and r.json()["Items"][0]["Type"] == "Series":
            seasonId = None    
            itemType = r.json()["Items"][0]["Type"]
            itemId = r.json()["Items"][0]["Id"]
            
            r = requests.get('https://palmtree.com.ar/emby/Users/' + adminId + '/Items?ParentId='+ itemId +'&Recursive=true&IncludeItemTypes=Season&api_key=' + embyApiKey)
            seasonsFound = r.json()["Items"]

            for index in range(len(seasonsFound)):
                if str(seasonsFound[index]["IndexNumber"]) == str(sonarrEpisodeSeasonNumber):
                    seasonId = seasonsFound[index]["Id"]

            if not seasonId:
                    logging.info('Season not found. Refreshing library in 30s')
                    time.sleep(30)
                    libraryRefreshRequest(imdbId)
            else:
                    r = requests.get('https://palmtree.com.ar/emby/Users/' + adminId + '/Items?ParentId='+ seasonId +'&Recursive=true&IncludeItemTypes=Episode&api_key=' + embyApiKey)
                    episodesFound = r.json()["Items"]

                    episodeNotFound = False

                    for index in range(len(episodesFound)):
                        episodeIndexNumber = episodesFound[index]["IndexNumber"]

                        if str(episodeIndexNumber) == str(sonarrEpisodeNumber) and "LocationType" not in episodesFound[index]:
                            logging.info("Episode found!! Quitting script...")
                            episodeNotFound = False
                            break
                        else:
                            episodeNotFound = True
                    
                    if episodeNotFound == True:
                        logging.info('Episode not found. Refreshing library in 30s')
                        time.sleep(30)  
                        libraryRefreshRequest(imdbId)
                                
        elif "Type" in r.json()["Items"][0] and r.json()["Items"][0]["Type"] == "Movie":
             logging.info('Movie found!! Quitting script...')

    # api call to local rclone with current transfers
    def checkUpload(host, srcFileName, title, imdbId):
        r = requests.post(host, auth=('joaquin', '40575566'))

        def checkFilmList(item):
                rcloneFileName = os.path.basename(item["name"])
                if rcloneFileName == srcFileName:
                        return True
                else:
                        return False

        try:
                film = list(filter(checkFilmList, r.json()["transferring"]))

                if len(itemFile) == 0:
                        itemFile.append(film[0])
                
                if len(film) > 0:
                        uploadSpeed = round(film[0]["speedAvg"] / 1000000, 2)
                        logging.info(f'{film[0]["percentage"]}%' + " " + film[0]["name"] + " " + str(uploadSpeed) + " MB/s")
                        itemFile[0]["percentage"] = film[0]["percentage"]
                        time.sleep(2)
                        checkUpload(host, srcFileName, title, imdbId)
                else:
                        embyRequest(imdbId)

        except KeyError as e:
                if len(itemFile) > 0 and itemFile[0]["percentage"] >= 98:
                    embyRequest(imdbId)
                elif len(itemFile) > 0 and itemFile[0]["percentage"] < 98:
                    print('Incomplete upload - Retry')
                    time.sleep(2)
                    checkUpload(host, srcFileName, title, imdbId)
                else:
                    print('No upload')
                    time.sleep(2)
                    checkUpload(host, srcFileName, title, imdbId)


    if radarrFileName:
        logging.basicConfig(filename=dir_path + '/logs/radarr/' + str(movieTitle) + '.log', level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%d-%m-%Y %H:%M:%S')
        logging.info("radarrFileName: " + str(radarrFileName))
        logging.info("movieTitle: " + str(movieTitle))

        time.sleep(2)
        host = "http://172.7.0.1:5572/core/stats"
        checkUpload(host, radarrFileName, movieTitle, movieImdbId)
    elif sonarrFileName:
        sonarrFileName = os.path.basename(sonarrFileName)

        logging.basicConfig(filename=dir_path + '/logs/sonarr/'+ str(sonarrFileName) + '.log', level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%d-%m-%Y %H:%M:%S')
        logging.info("sonarrFileName: " + str(sonarrFileName))
        logging.info("sonarrSeriesTitles: " + str(sonarrSeriesTitles))

        time.sleep(2)
        host = "http://172.7.0.1:5570/core/stats"
        checkUpload(host, sonarrFileName, sonarrSeriesTitles, sonarSeriesImdbId)
    else:
        print("nothin'")

if __name__ == "__main__":

    main()