from random import shuffle

from deuces.card import Card
from deuces.deck import Deck
from deuces.evaluator import Evaluator

class WrapDeck():

    def __init__(self):
        self.deck = Deck()

    def shuffle(self):
        shuffle(self.deck.cards)

    def shuffle_and_encrypt(self, key):
        self.shuffle()
        self.deck.cards = list(map(lambda b: b + key, self.deck.cards))
