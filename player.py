import threading
import time
from collections import deque

import Pyro4
from Pyro4.errors import ConnectionClosedError, CommunicationError
from deuces.card import Card
from deuces.deck import Deck
from deuces.evaluator import Evaluator


def start_thread(target, args=()):
    thread = threading.Thread(target=target, args=args)
    thread.setDaemon(True)
    thread.start()




def connection_decorator(func):
    def wrap_func(self, *args, **kwargs):
        while True:
            try:
                return func(self, *args, **kwargs)
            except CommunicationError as e:
                self.detect_failures()

    return wrap_func


@Pyro4.expose
class Player:
    def __init__(self, name, leader):
        self.name_value = name
        self.players = []
        self.uri = ''
        self.leader = leader
        self.state = 0
        self.dict_mutex = threading.Lock()

        """ States are:
        0 is registering phase
        1 is deck shuffling with common key
        2 is cards distributing between players(2 cards)
        3 is referee sequentially ask players to make bet(bet, pass, check)
        4 is referee ends with first betting and shows 3 first cards on board
        5 is referee sequentially getting decisions as in 3rd state
        6 is referee gives 4th card on board
        7 is referee get decisions
        8 is referee gives last card on deck 
        9 is referee gather desisions(after it he compute all scores and send them)
        10 is players are waiting for new referee
        """

    def ping(self):
        return {'pong': 'pong'}

    @property
    def name(self):
        return self.name_value

    @property
    def is_leader(self):
        return self.leader

    def set_uri(self, uri):
        self.uri = uri
        me = Pyro4.Proxy(uri)
        self.players = [me]

    @property
    def __str__(self):
        return self.name

    @property
    def money(self):
        return self.money_amount

    def is_self(self, other):
        return self.name == other.name

    # @Pyro4.oneway
    # def add_money(self, value):
    #     self.money_amount += value
    #
    # @Pyro4.oneway
    # def subtract_money(self, value):
    #     self.money_amount -= value

    def get_player_by_name(self, name):
        for player in self.players:
            if player.name == name:
                return player
        return None

    def detect_failures(self):
        players = self.players
        for player in players:
            try:
                res = player.ping()
                if res['pong'] != 'pong':
                    self.proceed_failured_node(player)
            except CommunicationError:
                self.proceed_failured_node(player)

    def clean_dicts(self):

        print('cleaning')
        self.dict_mutex.acquire()
        # print('acuired in clean')
        old_res_dict = self.players_with_cards
        old_mode_dict = self.players_with_modes
        self.players_with_modes = {}
        self.players_with_cards = {}
        try:
            for player in self.players:
                self.players_with_cards[player.name] = old_res_dict[player.name]
                self.players_with_modes[player.name] = old_mode_dict[player.name]
        except CommunicationError:
            self.players_with_modes = old_mode_dict
            self.players_with_cards = old_res_dict
            self.dict_mutex.release()
            # print('released in clean exp')

            self.detect_failures()
        self.dict_mutex.release()
        # print('released in clean')
        # print('cleaning end')

    def proceed_failured_node(self, node):
        failured_player = node
        try:
            self.players.remove(failured_player)
        except ValueError:
            pass
        self.clean_dicts()
        for player in self.players:
            try:
                player.notify_about_faulure()
            except CommunicationError:
                self.proceed_failured_node(player)

    @Pyro4.oneway
    def notify_about_faulure(self):
        # print('detecting start')
        self.detect_failures()
        # print('detecting end')


    @connection_decorator
    def ask_to_play_to(self, player_uri):
        # print('I am %s and i am in ask_to_play_to' % self.name)
        if self.state == 0:
            other = Pyro4.Proxy(player_uri)
            topology = other.ask_to_play_with(self.uri)
            self.players = list(topology)
            start_thread(self.cond_start)
        else:
            raise ValueError("Can not register while playing")

    @connection_decorator
    def ask_to_play_with(self, player_uri):
        # print('I am %s and i am in ask_to_play_with' % self.name)
        if self.state == 0:
            other = Pyro4.Proxy(player_uri)
            new_topology = deque([other] + self.players)
            self_players = new_topology.copy()
            new_topology.rotate(-1)
            # print('topology for new')
            # print(list(map(lambda x: x.name, list(new_topology))))
            resulted = new_topology.copy()
            for player in self.players:
                if not self.is_self(player):
                    # print('topology for %s' % player.name)
                    # print(list(map(lambda x: x.name, list(new_topology))))
                    new_topology.rotate(-1)
                    player.notify_about_new_player(new_topology)
            self.players = list(self_players)
            start_thread(self.cond_start)

            return resulted
        else:
            raise ValueError("Can not register while playing")

    @Pyro4.oneway
    @connection_decorator
    def notify_about_new_player(self, topology):
        if self.state == 0:
            self.players = list(topology)
            start_thread(self.cond_start)
        else:
            raise ValueError("Can not register while playing")

    @connection_decorator
    def cond_start(self):
        if len(self.players) == 4 and self.is_leader:
            self.start_game()

    def gathering_of_result(self):
        error = False
        while len(self.players_with_cards[self.name]) != 3:
            # print('Len of array is %d' % len(self.players_with_cards[self.name]))
            result = int(input('Enter one of three numbers:'))
            self.players_with_cards[self.name].append(result)
            for player in self.players:
                try:
                    player.share_result(result, self.name)
                except CommunicationError:
                    error = True
            if error:
                self.detect_failures()
                error = False
        if self.players_with_modes[self.name] is None:
            # print(self.players_with_modes)
            mode = int(input('Enter your mode value:'))
            self.players_with_modes[self.name] = mode
            for player in self.players:
                try:
                    player.share_mode(mode, self.name)
                except CommunicationError:
                    error = True
            if error:
                self.detect_failures()
                error = False

    @Pyro4.oneway
    @connection_decorator
    def start_game(self):
        if self.state == 0:
            self.state = 1
            self.players_with_cards = {}
            self.players_with_modes = {}
            for player in self.players:
                self.players_with_modes[player.name] = None
                self.players_with_cards[player.name] = []
            self.players_with_cards[self.name] = []
            self.players_with_modes[self.name] = None

            for player in self.players:
                if player.name != self.name:
                    player.start_game()
            self.gathering_of_result()

    @Pyro4.oneway
    @connection_decorator
    def share_result(self, result, sharer_name):
        print('I am in res, res is %d name is %s' % (result, sharer_name))
        self.dict_mutex.acquire()
        # print('acquire in result')

        if self.state != 1:
            raise ValueError('Only at first state game is allowed')
        if sharer_name != self.name:
            if len(self.players_with_cards[sharer_name]) < 3:
                self.players_with_cards[sharer_name].append(result)
            else:
                raise ValueError('Only 3 digits are allowed')
        self.dict_mutex.release()
        # print('released in result')

        self.detect_end()

    @Pyro4.oneway
    @connection_decorator
    def share_mode(self, mode, player_name):
        self.dict_mutex.acquire()
        # print('acquire in mode')

        print('I am in mode, mode is %d name is %s' % (mode, player_name))
        if self.state != 1:
            raise ValueError('Only at first state game is allowed')

        if player_name != self.name:

            if self.players_with_modes[player_name] is not None:
                raise ValueError('Mode can be provided only once')

            self.players_with_modes[player_name] = mode
        self.dict_mutex.release()
        # print('released in mode')

        self.detect_end()

    def detect_end(self):
        end = True
        self.dict_mutex.acquire()
        # print('acquire in detect end')

        # print(self.players_with_modes)
        # print(self.players_with_cards)
        for player_name, res in self.players_with_cards.items():
            if len(self.players_with_cards[player_name]) < 3:
                end = False
        for player_name, res in self.players_with_modes.items():
            if self.players_with_modes[player_name] is None:
                end = False

        if end:
            print('end is coming')
            common_mode = 0
            for player_name, mode in self.players_with_modes.items():
                common_mode += mode
            common_mode = round(common_mode / len(self.players))
            players_sums = {}
            for player_name, results in self.players_with_cards.items():
                players_sums[player_name] = sum(results) / common_mode
            min = None
            winner_name = None
            for player_name, result in players_sums.items():
                print('Player "%s" got %.2f as a result' % (player_name, result))
                if not min or result < min:
                    winner_name = player_name
                    min = result
            print('Winner is %s with %.2f points' % (winner_name, min))
        self.dict_mutex.release()
        # print('released in detect end')


    def print_players(self):
        players_to_print = list(map(lambda pl: pl.name, self.players))
        print(players_to_print)
