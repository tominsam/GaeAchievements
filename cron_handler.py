import os, sys
import logging
from datetime import datetime, timedelta

from google.appengine.ext import webapp
from google.appengine.api.labs import taskqueue

from model import *
import fetcher

class HourlyCron(webapp.RequestHandler):
    def get(self):
        logging.info("cron handler fired")
        guilds = Guild.all( keys_only = True ).filter( "last_fetch =", None ).fetch(100)
        guilds += Guild.all( keys_only = True ).filter( "last_fetch <", datetime.utcnow() - timedelta( hours = 3 ) ).fetch(100)
        for g in guilds:
            taskqueue.add(url='/fetcher/guild/', params={'key': str(g)})
            self.response.out.write("queued %s"%g)
        
        characters = Character.all( keys_only = True ).filter( "last_fetch =", None ).fetch(100)
        # schedule at most 100 chars an hour
        if len(characters) < 100:
            characters += Character.all( keys_only = True ).filter( "last_fetch <", datetime.utcnow() - timedelta( hours = 3 ) ).fetch( 100 - len(characters) )
        for c in characters:
            taskqueue.add(url='/fetcher/character/', params={'key': str(c)})
            self.response.out.write("queued %s"%c)

