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

def populate_achievement_objects( achievement_data ):
    lookup_ids = []
    for a in achievement_data:
        lookup_ids.append( [ a['achievement_id'] ] )
    looked_up = Achievement.lookup_many_cached( lookup_ids )
    for a in achievement_data:
        a["achievement"] = looked_up[ Achievement.key_name(a['achievement_id']) ]

class BaseHandler(webapp.RequestHandler):
    def render( self, template_name, vars ):
        template = jinja2_env.get_template(template_name)
        vars['users'] = users
        vars['user'] = users.get_current_user()
        self.response.out.write(template.render(vars))

    def paginate(self, achievement_data):
        total = len(achievement_data)
        limit = 20
        total_pages = int(total / limit) + 1
        try:
            page = int(self.request.get("page"))
        except ValueError:
            page = 1
        if page < 1: page = 1
        offset = ( page - 1 ) * limit

        # limit to most recent entries
        def by_date(a, b):
            return cmp(b['date'], a['date'])
        achievement_data.sort(by_date)
        achievement_data = achievement_data[offset:offset+limit]

        populate_achievement_objects( achievement_data )
        
        # TODO - it could be nice to populate Character objects here like we do
        # with achievmenet objects.
        
        
        return { "achievement_data":achievement_data, "page":page, "total_pages":total_pages }

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
        
        achievement_data = guild.unified_achievement_list()
        
        template_vars = self.paginate( achievement_data )

        template_vars["guild"] = guild
        self.render( "guild.html", template_vars )

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

        achievement_data = guild.unified_achievement_list()

        achievement_data = filter(lambda d: d['achievement_id'] == achievement.armory_id, achievement_data)
        
        template_vars = self.paginate( achievement_data )
        template_vars["guild"] = guild
        template_vars["achievement"] = achievement
    
        self.render( "guild_achievement.html", template_vars )

class CharacterHandler(BaseHandler):

    def get(self, continent, realm, urltoken):
        character = Character.lookup( continent, realm, urltoken )
        if not character:
            return self.error(404)
        
        achievement_data = []
        for achievement_id, date in zip( character.achievement_ids, character.achievement_dates ):
            achievement_data.append({
                "date":date.date(),
                "character_name":character.name,
                "character_url":character.url(),
                "achievement_id":achievement_id, # look up objects _after_ list truncate
            })
    
        template_vars = self.paginate( achievement_data )
        template_vars["guild"] = character.guild
        template_vars["character"] = character
        self.render( "character.html", template_vars )

