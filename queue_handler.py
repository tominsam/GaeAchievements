import os, sys
import logging

from google.appengine.ext import webapp
from google.appengine.api.labs import taskqueue

from model import *
import fetcher

class GuildFetcher(webapp.RequestHandler):
    def post(self):
        key = self.request.get('key')
        guild = Guild.get( key )
        fetcher.guild( guild )

class CharacterFetcher(webapp.RequestHandler):
    def post(self):
        key = self.request.get('key')
        character = Character.get( key )
