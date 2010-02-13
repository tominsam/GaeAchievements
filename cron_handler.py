import os, sys
import logging
from datetime import datetime, timedelta

from google.appengine.ext import webapp
from google.appengine.api.labs import taskqueue

from model import *
import fetcher

class HourlyCron(webapp.RequestHandler):
    def post(self):
        guilds = Guild.all().filter( "last_fetch =", None ).fetch(100)
        guilds += Guild.all().filter( "last_fetch <", datetime.now() - timedelta( hours = 3 ) ).fetch(100)
        for g in guilds:
            taskqueue.add(url='/fetcher/guild', params={'key': g.key()})
            
        characters = Character.all().filter( "last_fetch =", None ).fetch(100)
        characters += Character.all().filter( "last_fetch <", datetime.now() - timedelta( hours = 3 ) ).fetch(100)
        for c in characters:
            taskqueue.add(url='/fetcher/character', params={'key': c.key()})
            
        
