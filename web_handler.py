import os, sys
import logging

from google.appengine.ext import webapp
from google.appengine.api.labs import taskqueue
from google.appengine.api import users

from model import *

from jinja2 import Environment, FileSystemLoader
jinja2_env = Environment(
    loader=FileSystemLoader('templates'),
    line_statement_prefix="#",
    autoescape=True
)

def build_achievement_list( characters, limit = 20, offset = 0 ):
    achievement_data = []
    for character in characters:
        for achievement_id, date in zip( character.achievement_ids, character.achievement_dates ):
            achievement_data.append({
                "date":date.date(),
                "character":character,
                "achievement_id":achievement_id, # look up objects _after_ list truncate
            })
    
    # limit to most recent entries
    def by_date(a, b):
        return cmp(b['date'], a['date'])
    achievement_data.sort(by_date)
    achievement_data = achievement_data[offset:offset+limit]
    
    for a in achievement_data:
        a["achievement"] = Achievement.lookup_cached( a['achievement_id'] )
        
    return achievement_data
    
class BaseHandler(webapp.RequestHandler):
    def render( self, template_name, vars ):
        template = jinja2_env.get_template(template_name)
        vars['users'] = users
        vars['user'] = users.get_current_user()
        self.response.out.write(template.render(vars))

class RootHandler(BaseHandler):

    def get(self):
        guilds = Guild.all().order('name')
        self.render( "root.html", locals() )

    def post(self):
        delete = self.request.get("delete")
        if delete:
            g = Guild.get( delete )
            if users.is_current_user_admin() or g.owner == users.get_current_user():
                # the character fetcher deletes the characters once it notices that their
                # guild is gone - this makes the delete step here faster.
                g.delete()
            return
        
        if not users.get_current_user():
            return self.redirect("/")

        continent = self.request.get("continent")
        realm = self.request.get("realm")
        guildname = self.request.get("guild")

        guild = Guild.find_or_create( continent, realm, guildname )
        guild.owner = users.get_current_user()
        guild.put()
        if not guild:
            return self.error(404)
        taskqueue.add(url='/fetcher/guild/', params={'key': guild.key()})
        
        self.redirect( guild.url() )

class GuildMainHandler(BaseHandler):

    def get(self, continent, realm, urltoken):
        guild = Guild.lookup_cached( continent, realm, urltoken )
        if not guild:
            return self.error(404)
        
        limit = 20
        ids = []
        for c in guild.character_set: ids += c.achievement_ids
        total_pages = int(len(ids) / limit) + 1
        try:
            page = int(self.request.get("page"))
        except ValueError:
            page = 1
        if page < 1: page = 1
        offset = ( page - 1 ) * limit
        
        achievement_data = build_achievement_list( guild.character_set, limit = limit, offset = offset )


        self.render( "guild.html", locals() )

class GuildMembersHandler(BaseHandler):

    def get(self, continent, realm, urltoken):
        guild = Guild.lookup_cached( continent, realm, urltoken )
        if not guild:
            return self.error(404)
        self.render( "members.html", locals() )

class GuildAchievementHandler(BaseHandler):

    def get(self, continent, realm, urltoken, achievement_id):
        guild = Guild.lookup_cached( continent, realm, urltoken )
        achievement = Achievement.lookup_cached( achievement_id )
        if not achievement and guild:
            return self.error(404)
        
        achievement_data = []
        for character in guild.character_set.filter( "achievement_ids =", achievement.armory_id ):
            for achievement_id, date in zip( character.achievement_ids, character.achievement_dates ):
                if achievement_id == achievement.armory_id:
                    achievement_data.append({
                        "date":date.date(),
                        "character":character,
                        "achievement":achievement,
                    })

        def by_date(a, b):
            return cmp(b['date'], a['date'])
        achievement_data.sort(by_date)
    
        self.render( "guild_achievement.html", locals() )

class CharacterHandler(BaseHandler):

    def get(self, continent, realm, urltoken):
        character = Character.lookup( continent, realm, urltoken )
        if not character:
            return self.error(404)
        
        limit = 20
        total_pages = int(len(character.achievement_ids) / limit) + 1
        try:
            page = int(self.request.get("page"))
        except ValueError:
            page = 1
        if page < 1: page = 1
        offset = ( page - 1 ) * limit

        achievement_data = build_achievement_list( [ character ], limit = limit, offset = offset )

        self.render( "character.html", locals() )

