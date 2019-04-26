import sys
import threading

import Pyro4

from player import Player

def run_ask_to_play():
    player.ask_to_play_to(player_uri)


sys.excepthook = Pyro4.util.excepthook

self_name = input('Enter your name:').strip()

player_uri = input('Enter other player uri to play with. Or leave empty or write no to create lobby:').strip()

with Pyro4.Daemon() as daemon:
    if player_uri in ['', 'no']:
        player = Player(self_name, True)
    else:
        player = Player(self_name, False)

    self_player_uri = daemon.register(player)
    player.set_uri(self_player_uri)
    print(self_player_uri)

    if player_uri not in ['', 'no']:
        thread = threading.Thread(target=run_ask_to_play)
        thread.setDaemon(True)
        thread.start()

    print('strating')
    daemon.requestLoop()
    print('Ended')

print('Goodbuy')
