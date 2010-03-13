import os, sys
import logging

from google.appengine.ext import webapp
from google.appengine.api.labs import taskqueue

from model import *
import fetcher
import mailer

class GuildFetcher(webapp.RequestHandler):
    def post(self):
        try:
            key = self.request.get('key')
            guild = Guild.get( key )
            if guild:
                fetcher.guild( guild )
        except Exception, e:
            self.response.out.write(e)
            raise

class CharacterFetcher(webapp.RequestHandler):
    def post(self):
        try:
            key = self.request.get('key')
            character = Character.get( key )
            if character:
                fetcher.character( character.guild, character )
        except Exception, e:
            self.response.out.write(e)
            raise

class GuildMailer(webapp.RequestHandler):
    def post(self):
        try:
            key = self.request.get('key')
            guild = Guild.get( key )
            if guild:
                mailer.send_weekly_summary( guild, request = self.request )
        except Exception, e:
            self.response.out.write(e)
            raise
