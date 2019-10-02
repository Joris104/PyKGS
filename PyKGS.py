import json
import requests
import threading
import queue
import copy
import time

class KGSHandler:

    __cookie__ = ""
    __games__ = {}
    _kgsURL_ = 'http://www.gokgs.com/json/access'
    __threads__ = list()
    gamesLock = threading.Lock()
    ##Constructor
    def __init__(self, login, password,globalGameList):
        #Login to the server
        message_login = {
        "type": "LOGIN",
        "name": login,
        "password": password,
        "locale": "fr_FR"
        }
        r = requests.post(self._kgsURL_,data=json.dumps(message_login))
        #Check if we could connect
        if r.status_code == 200:
            #If successful, we start regularly polling KGS for updates
            self.__cookie__ = r.cookies
            if globalGameList:
                self.__joinGlobalGameList__()
            self.__startDaemons__()
        else:
            raise Exception("Could not connect to the KGS server - either the server is down, or the connection information was not valid")
    
    def __del__(self):
        print("deleting Handler")
        self.close()

    ##Private functions
    def __communicationDaemon__(self, message_queue) :
        #Periodically sends a GET message to KGS. The response contains updated information, which are processed in messageHandler
        while True:
            r = requests.get(self._kgsURL_, cookies=self.__cookie__, timeout=60)
            if r.status_code !=  200 :
                raise Exception("Connection to the KGS server was lost")
            
            messages = r.json()["messages"]
            for m in messages:
                message_queue.put(m)
            time.sleep(5)

    def __messageHandler__(self, message_queue):
        #Processes the messages received by KGS
        #Currently only processes new games
        while True:
            m = message_queue.get()
            if (m["type"] == "ROOM_JOIN" or m["type"] == "GAME_LIST") and "games" in m:
                for g in m["games"]:
                    if (g["gameType"] == "free" or  g["gameType"] == "ranked"):
                        black = g["players"]["black"]["name"]
                        white = g["players"]["white"]["name"]
                        id = g["channelId"]
                        moveNum = g["moveNum"]
                        if "score" in g:
                            score = g["score"]
                        else:
                            score = "UNFINISHED"
                        self.gamesLock.acquire()
                        self.__games__[id] = {
                            "id"       : id,
                            "black"    : black, 
                            "white"    : white, 
                            "moveNum" : moveNum,
                            "score"    : score       }
                        self.gamesLock.release()
            message_queue.task_done()

    def __startDaemons__(self):
        message_queue = queue.Queue()
        threads = [self.__communicationDaemon__, 
                  self.__messageHandler__]
        for t in threads:
            x = threading.Thread(target=t,args=(message_queue,), daemon=True)
            self.__threads__.append(x)
            x.start()

    def __joinGlobalGameList__ (self):
        message = {
        "type": "GLOBAL_LIST_JOIN_REQUEST",
        "list": "ACTIVES"
        }
        r = requests.post(self._kgsURL_,cookies = self.__cookie__, data=json.dumps(message))
        if r.status_code != 200:
            raise Exception("Could not join Global Game List")
    
    ##Public functions
    def getGames (self):
        #returns an array of the games currently being played on the server
        #return format :
        #Array of dictionaries of the form {"id":id, "black" : black, "white" : white, "moveNum" : moveNum, "score": score}
        #id is the id of the game
        #black & white are the name of the players
        #moveNum is the number of moves played if the game is currently underway
        #score is the score of the game, and either contains a number (positive : Black won, negative : White won) or a string
        #Possible score strings are UNKNOWN, UNFINISHED, NO_RESULT, B+RESIGN, W+RESIGN, B+FORFEIT, W+FORFEIT, B+TIME, or W+TIME
        #B+ stands for "Black wins" W+ for "White wins"
        #Poll this regularly
        self.gamesLock.acquire()
        r = self.__games__.values()
        self.gamesLock.release()
        return r
    
    def close(self):
        #Closes the connection
        message = {
        "type": "LOGOUT"
        }

        requests.post(self._kgsURL_,cookies = self.__cookie__, data=json.dumps(message))
        print("Closed the connection")
def __init__(self):
    pass