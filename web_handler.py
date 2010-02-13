import os, sys
import logging


from google.appengine.ext import webapp
from google.appengine.api.labs import taskqueue
import itertools

from model import *

from jinja2 import Environment, FileSystemLoader
jinja2_env = Environment(
    loader=FileSystemLoader('templates'),
    line_statement_prefix="#",
    autoescape=True
)

class BaseHandler(webapp.RequestHandler):
    def render( self, template_name, vars ):
        template = jinja2_env.get_template(template_name)
        self.response.out.write(template.render(vars))

class RootHandler(BaseHandler):

    def get(self):
        guilds = Guild.all().order('name')
        self.render( "root.html", locals() )

    def post(self):
        continent = self.request.get("continent")
        realm = self.request.get("realm")
        guildname = self.request.get("guild")

        guild = Guild.find_or_create( continent, realm, guildname )
        if not guild:
            return self.error(404)
        taskqueue.add(url='/fetcher/guild', params={'key': guild.key()})
        
        self.redirect( guild.url() )

class GuildMainHandler(BaseHandler):

    def get(self, continent, realm, urltoken):
        guild = Guild.lookup( continent, realm, urltoken )
        if not guild:
            return self.error(404)
        
        achievement_data = []
        for character in guild.character_set:
            for achievement_id, date in zip( character.achievement_ids, character.achievement_dates ):
                achievement_data.append({
                    "date":date.date(),
                    "achievement":Achievement.lookup( achievement_id ),
                    "character":character,
                })
        self.render( "guild.html", locals() )

class GuildMembersHandler(BaseHandler):

    def get(self, continent, realm, urltoken):
        guild = Guild.lookup( continent, realm, urltoken )
        if not guild:
            return self.error(404)
        self.render( "members.html", locals() )

class GuildAchievementHandler(BaseHandler):

    def get(self, continent, realm, urltoken, achievement_id):
        guild = Guild.lookup( continent, realm, urltoken )
        achievement = Achievement.lookup( achievement_id )
        if not achievement and guild:
            return self.error(404)
        self.render( "guild_achievement.html", locals() )

class CharacterHandler(BaseHandler):

    def get(self, continent, realm, urltoken):
        character = Character.lookup( continent, realm, urltoken )
        if not character:
            return self.error(404)

        achievement_data = []
        for achievement_id, date in zip( character.achievement_ids, character.achievement_dates ):
            achievement_data.append({
                "date":date.date(),
                "achievement":Achievement.lookup( achievement_id ),
                "character":character,
            })
            
        def date_order(a,b):
            return cmp( b['date'], a['date'] )
        achievement_data.sort(date_order)
        
        logging.info("found %s achievments"%( len(achievement_data)))

        self.render( "character.html", locals() )

