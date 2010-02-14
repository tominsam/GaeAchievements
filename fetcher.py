import md5
from datetime import datetime, timedelta
from google.appengine.api import urlfetch
import urllib
import xmltramp
import sys
import logging
import iso8601

from google.appengine.ext import db
from google.appengine.api import datastore_errors
from google.appengine.api.labs import taskqueue

from model import *
#import debug

class FetchError(Exception):
    pass

class NotFoundError(FetchError):
    pass

def fetch( url ):
    # Need to specify firefox as user agent as this makes the server return an XML file.
    
    try:
        result = urlfetch.fetch(
            url = url,
            headers = { "User-Agent":'Mozilla/5.0 (Windows; U; Windows NT 5.0; en-GB; rv:1.8.1.4) Gecko/20070515 Firefox/2.0.0.4' }
        )
    except urlfetch.DownloadError, e:
        logging.error("DownloadError fetching %s: %s"%( url, e ))
        raise FetchError()
    
    if str(result.status_code)[0] == '4':
        raise NotFoundError()

    if result.status_code == 200:
        return xmltramp.parse( result.content )
    
    logging.info("fetch code %s fetching %s"%( result.status_code, url ))
    logging.info( result.content )
    
    raise FetchError()


def guild( guild, force = False ):
    
    try:
        xml = fetch( guild.armory_url() )
    except NotFoundError:
        guild.fetch_error = "Can't find armoury URL."
        guild.last_fetch = datetime.utcnow()
        guild.put()
        return
    except FetchError:
        guild.fetch_error = "Error fetching URL from armory."
        guild.last_fetch = datetime.utcnow()
        guild.put()
        return

    guild.fetch_error = None
    found = []
    dirty_characters = []
    needs_refresh = []
    
    # set these properties here so that we avoid capitalization errors in user input
    guild.name = xml['guildInfo']['guildHeader']('name')
    guild.realm = xml['guildInfo']['guildHeader']('realm')

    for character_xml in xml['guildInfo']['guild']['members']['character':]:
        name = character_xml('name')
        logging.info( "seen character %s in XML (%s)"%( name, character_xml.__repr__(1) ) )
        character = Character.find_or_create( guild.continent, guild.realm, name )
        dirty = False
        try:
            if (not character.guild) or (character.guild != guild):
                logging.info("guild changed: %s != %s"%( character.guild, guild ))
                character.guild = guild
                dirty = True
        except datastore_errors.Error:
            # can't fetch old guild object - deleted?
            character.guild = guild
            dirty = True

        for prop in ['raceId', "classId", "level", "rank"]:
            if getattr( character, prop ) != int(character_xml(prop)):
                setattr( character, prop, int(character_xml(prop)) )
                dirty = True

        if dirty:
            dirty_characters.append( character )

        found.append( character.key() )

        if not character.last_fetch or character.last_fetch < datetime.utcnow() - timedelta( hours = 2 ):
            needs_refresh.append( character.key() )
    
    for character in guild.character_set:
        if not character.key() in found:
            logging.info("removing character %s from guild"%( character.name ))
            character.guild = None
            found.append( character.key() )

    guild.last_fetch = datetime.utcnow()

    # save all characters at once.
    logging.info("saving %s characters"%len( dirty_characters ))

    db.put( dirty_characters + [ guild ] )

    logging.info("adding %s characters to refresh queue"%len( needs_refresh ))
    for key in needs_refresh:
        taskqueue.add(url='/fetcher/character/', params={'key': key})
    

def character( guild, character, force = False ):
    if not guild and not character.guild:
        # erase characters without a guild
        character.delete()
        return

    try:
        char_xml = fetch( character.armory_url() )
    except FetchError:
        raise
    
    char = char_xml['characterInfo']['character']
    character.achPoints = long(char('points'))
    
    added_count = 0
    try:
        for ach in char_xml['achievements']['summary']['achievement':]:
            achievement = Achievement.find_or_create( ach('id'), ach('title'), ach('desc'), ach('icon') )
            logging.info( "seen achievement %s"%( achievement.name ))
            if achievement.armory_id not in character.achievement_ids:
                logging.info( "adding achievement %s"%( achievement.name ))
                added_count += 1
                character.achievement_ids.append( achievement.armory_id )
                character.achievement_dates.append( iso8601.parse_date(ach("dateCompleted")) )

    except KeyError:
        # achievments key not present. No achievements.
        pass
        
    if added_count >= 5:
        # me might have missed some. We need a full backfill.
        return backfill( guild, character, char_xml )
    
    character.last_fetch = datetime.utcnow()
    character.put()

def backfill( guild, character, char_xml = None ):
    if not char_xml:
        try:
            char_xml = fetch( character.armory_url() )
        except FetchError:
            raise

    for category in char_xml['achievements']['rootCategories']:
        logging.info("   fetching category %s: %s"%( category('id'), category('name') ) )
        try:
            category_xml = fetch(character.armory_url() + u"&c=%s"%category("id") )
        except FetchError:
            raise
        
        for ach in category_xml['category']:
            # add completed achievements only:
            try: ach('dateCompleted') # raises keyerror
            except KeyError: continue

            achievement = Achievement.find_or_create( ach('id'), ach('title'), ach('desc'), ach('icon') )
            if achievement.armory_id not in character.achievement_ids:
                logging.info( "adding achievement %s"%( achievement.name ))
                character.achievement_ids.append( achievement.armory_id )
                character.achievement_dates.append( iso8601.parse_date(ach("dateCompleted")) )
    
    character.last_fetch = datetime.utcnow()
    character.put()



