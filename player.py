import threading
import time

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
        try:
            return func(self, *args, **kwargs)
        except CommunicationError as e:
            self.detect_failures()

            print(e)

    return wrap_func


@Pyro4.expose
class Player:
    def __init__(self, name, leader):
        self.name_value = name
        self.players = []
        self.uri = ''
        self.leader = leader
        self.state = 0
        self.money_amount = 10000
        self.is_referee = False
        """ States are:
        0 is registering phase
        1 is between game and new dealer selected
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

    @property
    def __str__(self):
        return self.name

    @property
    def money(self):
        return self.money_amount

    @Pyro4.oneway
    def add_money(self, value):
        self.money_amount += value

    @Pyro4.oneway
    def subtract_money(self, value):
        self.money_amount -= value

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

    def proceed_failured_node(self, node):
        failured_player = node
        self.players.remove(failured_player)
        self.active_players.remove(failured_player)
        for player in self.players:
            try:
                player.notify_about_faulure()
            except CommunicationError:
                self.proceed_failured_node(player)

    def notify_about_faulure(self):
        self.detect_failures()

    @connection_decorator
    def ask_to_play_to(self, player_uri):
        # print('I am %s and i am in ask_to_play_to' % self.name)
        if self.state == 0:
            other = Pyro4.Proxy(player_uri)
            self._add_player(other)
            other_players = other.ask_to_play_with(self.uri)
            for other_player in other_players:
                self._add_player(other_player)
        else:
            raise ValueError("Can not register while playing")

    @connection_decorator
    def ask_to_play_with(self, player_uri):
        # print('I am %s and i am in ask_to_play_with' % self.name)
        if self.state == 0:
            other = Pyro4.Proxy(player_uri)
            presented_players = self.players.copy()
            for player in presented_players:
                player.notify_about_new_player(other)
            self._add_player(other)
            print('New player in lobby: %s' % other.name)
            return presented_players
        else:
            raise ValueError("Can not register while playing")

    @Pyro4.oneway
    @connection_decorator
    def notify_about_new_player(self, other):
        if self.state == 0:
            print('New player in lobby: %s' % other.name)
            self._add_player(other)
        else:
            raise ValueError("Can not register while playing")

    @connection_decorator
    def cond_start(self):
        if len(self.players) == 3 and self.is_leader:
            self.start_game_as_leader()

    @connection_decorator
    def _add_player(self, other):
        # print('I am %s and i am in add_player' % self.name)
        if self.state == 0:
            self.players.append(other)
            start_thread(self.cond_start)
        else:
            raise ValueError("Can not register while playing")

    @connection_decorator
    def start_game_as_leader(self):
        if self.state != 0:
            raise ValueError('Only at registering phase you can start the game')
        elif not self.is_leader:
            raise ValueError('Only leader can start the game')
        time.sleep(1)
        for player in self.players:
            player.start_game()
        self.state = 1
        time.sleep(1)
        self.select_referee()

    @Pyro4.oneway
    @connection_decorator
    def start_game(self):
        # print('I am %s and i am in start_game' % self.name)
        if self.state != 0:
            raise ValueError('Only at registering phase the game can be started')
        else:
            self.state = 1
            print('The leader is looking for referee now')

    @Pyro4.oneway
    @connection_decorator
    def grant_referee(self):
        if self.state != 1 and self.state != 10:
            raise ValueError('Only at state 1 or 10, referee can be granted')
        self.is_referee = True
        print('You are new referee now')

    @connection_decorator
    def select_referee(self):
        if self.state != 1:
            raise ValueError('Only at state 1, referee can be granted')
        self.print_players()
        new_referee = None
        while not new_referee:
            referee_name = input('Enter new referee name:')
            new_referee = self.get_player_by_name(referee_name)
        if new_referee:
            new_referee.grant_referee()
            self.state = 2
            for player in self.players:
                print(player.name)
                player.end_referee_voting(new_referee)
            print('You have selected referee, the game is started')

        else:
            raise ValueError('Referees name have not found')

    @Pyro4.oneway
    @connection_decorator
    def end_referee_voting(self, referee):
        if self.state != 1 and self.state != 10:
            raise ValueError('End of referee election can be only at state 1 or 10, current is %d' % self.state)
        else:
            # print('I am %s and i am in end_referee_voting' % self.name)

            self.state = 2
            self.referee = referee
            print('New referee is %s, the game is started' % referee.name)
            if self.is_referee:
                print('I am referee')
                self.deck = Deck()
                self.players_with_cards = {}
                time.sleep(1)
                print('After sleep')
                for player in self.players:
                    print(player.name)
                    self.give_cards_to_player(player)
                time.sleep(1)
                self.state = 3
                print('Now you will wait for players decisions')
                self.active_players = self.players
                self.bank = 0
                self.ask_for_decision_as_referee()

    @connection_decorator
    def give_cards_to_player(self, player):
        if self.state != 2:
            raise ValueError('Only at second state referee can give cards')
        cards_to_give = self.deck.draw(n=2)
        self.players_with_cards[player] = cards_to_give
        player.get_cards(cards_to_give)

    @Pyro4.oneway
    @connection_decorator
    def get_cards(self, cards):
        if self.state != 2:
            raise ValueError('Only at second state referee can give cards')
        self.hand_cards = cards
        print('You got next cards on hands')
        Card.print_pretty_cards(cards)

    @Pyro4.oneway
    @connection_decorator
    def begin_gathering_of_decisions(self):
        if self.state == 2:
            self.state = 3
            print('You got the cards on hands, now referee gathers your decisions')
        elif self.state == 4:
            self.state = 5
            print('You got 3 cards on board, now referee gathers your decisions')
        elif self.state == 6:
            self.state = 7
            print('You got the 4th card on board, now referee gathers your decisions')
        elif self.state == 8:
            self.state = 9
            print('You got the 5th card on board, now referee gathers your decisions')

    @connection_decorator
    def ask_for_decision_as_referee(self):
        if not self.is_referee:
            raise ValueError('Only referees can gather decisions')
        if self.state not in [3, 5, 7, 9]:
            raise ValueError('Gathering of decisions can be done only at 3 5 7 9 states')

        for player in self.players:
            player.begin_gathering_of_decisions()
        time.sleep(1)

        self.max_bet = 0

        for player_to_ask in self.active_players:
            success = False
            while not success:
                try:
                    decision = player_to_ask.ask_for_decision()['decision']
                    if decision == 'pass':
                        self.active_players.remove(player_to_ask)
                    elif decision == 'check':
                        if self.max_bet > 0:
                            player_to_ask.subtract_money(self.max_bet)
                            self.bank += self.max_bet
                        else:
                            raise ValueError('You cannot check if you are the first')
                    elif decision.startswith('bet'):
                        value = int(decision.split(' ')[1])
                        player_to_ask.subtract_money(value)
                        self.bank += value
                        if value > self.max_bet:
                            self.max_bet = value
                    else:
                        raise ValueError('Cannot parse decision')

                    for player in self.players:
                        player.notify_about_decision(decision, player_to_ask)
                    success = True
                except (ValueError, IndexError):
                    success = False

        print('Gathering ends, going to next phase')
        if self.state != 9:
            self.state += 1
            for player in self.players:
                player.end_of_gathering_decision()
            self.put_cards_on_board_as_referee()
        else:
            self.end_the_game_as_referee()

    @connection_decorator
    def ask_for_decision(self):
        decision = input(
            'We are waiting for your decision. Print your decision in next format "pass" "check" "bet 10":')
        return {'decision': decision}

    @Pyro4.oneway
    @connection_decorator
    def end_of_gathering_decision(self):
        if self.state == 3:
            self.state = 4
            self.board = []
            print('Now you will get 3 cards on board')
        elif self.state == 5:
            self.state = 6
            print('Now you will get 1 more card on board')
        elif self.state == 7:
            self.state = 8
            print('Now you will get 1 more card on board')

    @Pyro4.oneway
    @connection_decorator
    def notify_about_decision(self, decision, player):
        print('Player %s: %s' % (player.name, decision))

    @connection_decorator
    def put_cards_on_board_as_referee(self):
        if self.state == 4:
            self.board = []
            num_cards = 3
        elif self.state == 6 or self.state == 8:
            num_cards = 1
        else:
            raise ValueError('It is not time to put cards on board')
        new_cards_for_board = self.deck.draw(num_cards)
        if num_cards == 1:
            new_cards_for_board = [new_cards_for_board]
        self.board += new_cards_for_board
        for player in self.players:
            player.put_cards_on_board(new_cards_for_board)
        print('Cards on board')
        time.sleep(1)
        self.state += 1
        for player in self.players:
            player.begin_gathering_of_decisions()
        self.ask_for_decision_as_referee()

    @Pyro4.oneway
    @connection_decorator
    def put_cards_on_board(self, cards):
        self.board += cards
        print('Now board cards are:')
        Card.print_pretty_cards(cards)

    @connection_decorator
    def end_the_game_as_referee(self):
        if self.state != 9:
            raise ValueError('Only at 9th state you can end the game')
        elif not self.is_referee:
            raise ValueError('Only referee can end the game')
        max_result = 0
        winner = None
        evaluator = Evaluator()
        for player, cards in self.players_with_cards.items():
            player_result = evaluator.evaluate(cards, self.board)
            if player_result > max_result:
                if player in self.active_players:
                    max_result = player_result
                    winner = player
        winner.add_money(self.bank)
        for player in self.players:
            player.end_the_game(winner, self.bank)
        self.state = 10
        self.select_new_referee()

    @connection_decorator
    def select_new_referee(self):
        if self.state != 10:
            raise ValueError('You can select referee only at 10th state')
        elif not self.is_referee:
            raise ValueError('Only referee can select new referee')
        self.print_players()
        new_referee = None
        while not new_referee:
            referee_name = input('Enter new referee name:')
            new_referee = self.get_player_by_name(referee_name)

        new_referee.grant_referee()
        for player in self.players:
            player.end_referee_voting(new_referee)
        self.state = 2
        self.is_referee = False
        del self.bank
        del self.board
        del self.active_players
        del self.players_with_cards
        del self.max_bet
        del self.deck

    @Pyro4.oneway
    @connection_decorator
    def end_the_game(self, player, bank):
        if self.state == 9:
            self.state = 10
            print('The game have been ended, the winner is %s player, his prize is %d' % (player.name, bank))
            del self.hand_cards
            del self.board

    @connection_decorator
    def print_players(self):
        players_to_print = list(map(lambda pl: pl.name, self.players))
        print(players_to_print)
