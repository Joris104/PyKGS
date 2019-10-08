import json
import requests
import threading
import queue
import copy
import time

class KGSHandler:
    #General info
    __cookie__ = ""
    _kgsURL_ = 'http://www.gokgs.com/json/access'

    #FLAGS
    __closeCommunication__ = False

    #internal memory
    
    __inQueue__ = queue.Queue()
    __outQueue__ = queue.Queue()

    __games__ = {}
    __gamesLock__ = threading.Lock()
    
    __threads__ = list()
    
    __archiveUser__ = ""
    __archiveGames__ = []
    __archiveLock__ = threading.Lock()

    __comments__ = []
    __commentsLock__ = threading.Lock()

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
    def __communicationDaemon__(self) :
        #Periodically sends a GET message to KGS. The response contains updated information, which are processed in messageHandler
        while True:
            if self.__closeCommunication__:
                return
            #Periodic GET requests
            r = requests.get(self._kgsURL_, cookies=self.__cookie__, timeout=60)
            if r.status_code !=  200 :
                raise Exception("Connection to the KGS server was lost")
            if "messages" in r.json():
                messages = r.json()["messages"]
                for m in messages:
                    self. __inQueue__.put(m)
            
            #Send POST messages if any are queued
            try:
                out_message = self.__outQueue__.get_nowait()
            except queue.Empty:
                time.sleep(1)
                continue
            r = requests.post(self._kgsURL_, cookies = self.__cookie__, data=json.dumps(out_message))
            if r.status_code != 200:
                raise Exception("Received a bad response after trying to post a message")
                
    def __gameChannelHandler__(self, message):
        #Puts all comments made during a game into the __comments__ list
        channelId = message["channelId"]
        sgfEvents = message["sgfEvents"]
        self.__commentsLock__.acquire()
        for e in sgfEvents:
            if e["type"] == "PROP_ADDED":
                p = e["prop"]
                if p["name"] == "COMMENT":
                        lines = p["text"].split("\n")
                        for l in lines:
                            if len(l) == 0:
                                continue
                            user, text = l.split(":")
                            if '[' in user:
                                user, rank = user.split(" ")
                            else :
                                rank = "NO_RANK"
                            self.__comments__.append(
                                {
                                    "channelId" : channelId,
                                    "user" : user,
                                    "rank" : rank,
                                    "text" : text[1:]
                                }
                            )
            if e["type"] == "PROP_GROUP_ADDED":
                for p in e["props"]:
                    if p["name"] == "COMMENT":
                        lines = p["text"].split("\n")
                        for l in lines:
                            if len(l) == 0:
                                continue
                            user, text = l.split(":")
                            if '[' in user:
                                user, rank = user.split(" ")
                            else :
                                rank = "NO_RANK"
                            self.__comments__.append(
                                {
                                    "channelId" : channelId,
                                    "user" : user,
                                    "rank" : rank,
                                    "text" : text[1:]
                                }
                            )
        self.__commentsLock__.release()

    def __messageHandler__(self):
        #Processes the messages received by KGS
        #Currently only processes games
        while True:
            m = self.__inQueue__.get()
            if (m["type"] == "GAME_JOIN") or (m["type"] == "GAME_UPDATE"):
                self.__gameChannelHandler__(m)
            ##ROOM_JOIN & GAME_LIST handling
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
                        self.__gamesLock__.acquire()
                        self.__games__[id] = {
                            "id"       : id,
                            "black"    : black, 
                            "white"    : white, 
                            "moveNum" : moveNum,
                            "score"    : score       }
                        self.__gamesLock__.release()
                    if g["gameType"] == "review":
                        id = g["channelId"]
                        #It is possible for a game to switch from "free" or "ranked" to "review"
                        #So we need to remove them from the games dict if that is the case
                        self.__gamesLock__.acquire()
                        self.__games__.pop(id,None)
                        self.__gamesLock__.release()
            ## GAME_CONTAINER_REMOVE_GAME handling
            if m["type"] == "GAME_CONTAINER_REMOVE_GAME":
                self.__gamesLock__.acquire()
                self.__games__.pop(m["gameId"],None)
                self.__gamesLock__.release()
            ## ARCHIVE_JOIN
            if m["type"] == "ARCHIVE_JOIN":
                self.__archiveLock__.acquire()
                self.__archiveUser__ = m["user"]["name"]
                for g in m["games"]:
                    #We do not return reviews
                    if (g["gameType"] == "free" or  g["gameType"] == "ranked"):
                        black = g["players"]["black"]["name"]
                        white = g["players"]["white"]["name"]
                        score = g["score"]
                        timestamp = g["timestamp"]

                        self.__archiveGames__.append( {
                            "timestamp" : timestamp,
                            "black" : black,
                            "white" : white,
                            "score" : score
                        })
                self.__archiveLock__.release()
            self.__inQueue__.task_done()

    def __startDaemons__(self):
        self.__threads__.append(threading.Thread(target=self.__communicationDaemon__, daemon=True))
        self.__threads__.append(threading.Thread(target=self.__messageHandler__, daemon=True))
        for t  in self.__threads__:
            t.start()

    def __joinGlobalGameList__ (self):
        message = {
        "type": "GLOBAL_LIST_JOIN_REQUEST",
        "list": "ACTIVES"
        }
        r = requests.post(self._kgsURL_,cookies = self.__cookie__, data=json.dumps(message))
        if r.status_code != 200:
            raise Exception("Could not join Global Game List")
    
    
    ##Public functions
    def getComments(self):
        self.__commentsLock__.acquire()
        r = copy.deepcopy(self.__comments__)
        self.__comments__ = []
        self.__commentsLock__.release()

        return r

    def joinChannel(self, channelId):
        #joins a channel
        message = {
            "type": "JOIN_REQUEST",
            "channelId": channelId
        }
        self.__outQueue__.put(message)

    def getGames (self):
        #returns an array of the games currently being played on the server
        #return format :
        #Array of dictionaries of the format 
        # {"id":id, "black" : black, "white" : white, "moveNum" : moveNum, "score": score}
        #id is the id of the game
        #black & white are the name of the players
        #moveNum is the number of moves played if the game is currently underway
        #score is the score of the game, and either contains a number (positive : Black won, negative : White won) or a string
        #Possible score strings are UNKNOWN, UNFINISHED, NO_RESULT, B+RESIGN, W+RESIGN, B+FORFEIT, W+FORFEIT, B+TIME, or W+TIME
        #B+ stands for "Black wins" W+ for "White wins"
        #Poll this regularly
        self.__gamesLock__.acquire()
        r = copy.deepcopy(list(self.__games__.values()))
        self.__gamesLock__.release()
        return r
    
    def getGamesFromUser(self, user):
        #WARNING : can take several seconds to return
        #Returns all the games played by the user on the KGS server over the last 6 months
        #Input:
        #user : string containing the username of the user whose archive we want
        #Output :
        #Array of dictionaries, of the format :
        #{"timestamp" : timestamp,
        # "black" : black
        # "white" : white
        # "score" : score}
        self.__archiveLock__.acquire()
        message = {
            "type": "JOIN_ARCHIVE_REQUEST",
            "name": user
        }
        self.__outQueue__.put(message)
        self.__archiveUser__ = ""
        self.__archiveLock__.release()
        while True:
            time.sleep(1)
            self.__archiveLock__.acquire()
            if self.__archiveUser__ == user:
                r = self.__archiveGames__.copy()
                self.__archiveLock__.release()
                return r
            self.__archiveLock__.release()

    def close(self):
        #Closes the connection
        message = {
        "type": "LOGOUT"
        }

        requests.post(self._kgsURL_,cookies = self.__cookie__, data=json.dumps(message))
        self.__closeCommunication__ =True
    
def __init__(self):
    pass