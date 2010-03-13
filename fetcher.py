import md5
from datetime import datetime, timedelta
from google.appengine.api import urlfetch
import urllib
import xmltramp
import sys
import logging
import iso8601

from cStringIO   import StringIO
from xml.etree   import cElementTree as etree


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
    return xmltramp.parse( fetch_raw( url ) )

def fetch_raw( url ):
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
        return result.content
    
    logging.error("fetch code %s fetching %s"%( result.status_code, url ))
    logging.info( result.content )
    
    raise FetchError()

def fetch_async( url ):
    # Need to specify firefox as user agent as this makes the server return an XML file.
    rpc = urlfetch.create_rpc()
    urlfetch.make_fetch_call(rpc,
        url = url,
        headers = { "User-Agent":'Mozilla/5.0 (Windows; U; Windows NT 5.0; en-GB; rv:1.8.1.4) Gecko/20070515 Firefox/2.0.0.4' }
    )
    return rpc


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
        logging.debug( "seen character %s in XML (%s)"%( name, character_xml.__repr__(1) ) )
        character = Character.find_or_create( guild.continent, guild.realm, name )
        dirty = False
        try:
            if (not character.guild) or (character.guild.key() != guild.key()):
                logging.info("guild for %s is changed or new"%character.name)
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

        # TODO - only do this for new characters? I worry about the race condition
        # where a guild is refreshed because of a cron run, because the characters
        # will have been queued for refresh at the same time
        if not character.last_fetch or character.last_fetch < datetime.utcnow() - timedelta( hours = 5 ):
            needs_refresh.append( character.key() )

    for character in guild.character_set:
        if not character.key() in found:
            logging.info("removing character %s from guild"%( character.name ))
            character.guild = None
            guild.remove_character_from_cache( character )
            found.append( character.key() )

    guild.last_fetch = datetime.utcnow()

    # save all characters at once.
    if len(dirty_characters):
        logging.info("saving %s characters"%len( dirty_characters ))
    db.put( dirty_characters + [ guild ] )

    if len(needs_refresh):
        logging.info("adding %s characters to refresh queue"%len( needs_refresh ))

    queue = taskqueue.Queue( name = "character" )
    for key in needs_refresh:
        task = taskqueue.Task( url='/fetcher/character/', params={'key': key} )
        queue.add(task)
    

def character( guild, character, force = False ):
    if not guild and not character.guild:
        # erase characters without a guild
        logging.info("deleting guildless character %s"%character.name)
        character.delete()
        return

    try:
        raw_xml = fetch_raw( character.armory_url() )
    except FetchError:
        logging.info("fetcherror")
        return # normally this is an armory failure. I'm not going to put clever handling in here.
    
    char_xml = xmltramp.parse( raw_xml )
    try:
        char = char_xml['characterInfo']['character']
    except KeyError:
        logging.info("keyerror")
        return # normally armoury error

    character.achPoints = long(char('points'))
    
    added_count = add_achievements( character, raw_xml )
    if added_count >= 5:
        logging.info("Seen at least 5 new achievements - running backfill")
        added_count = backfill( character, char_xml )
    
    logging.info("added %d achievements"%added_count)

    # otherwise we're done.
    character.last_fetch = datetime.utcnow()
    character.put()

    guild.update_achievements_cache_for( character )
    guild.put()

def backfill( character, char_xml = None ):
    if not char_xml:
        try:
            char_xml = fetch( character.armory_url() )
        except FetchError:
            return # normally an armory error
    
    fetches = []
    for category in char_xml['achievements']['rootCategories']:
        logging.info("   fetching category %s: %s"%( category('id'), category('name') ) )
        fetches.append( fetch_async( character.armory_url() + u"&c=%s"%category("id") ) )
    
    added = 0

    for rpc in fetches:
        try:
            result = rpc.get_result()
            if result.status_code == 200:
                logging.info("dequeued %s"%rpc)
                added += add_achievements( character, result.content )
            else:
                return # failed
        except urlfetch.DownloadError:
            return # failed.
    
    return added

def add_achievements( character, xml ):
    dom = etree.parse( StringIO(xml) )
    
    added = []
    for ach in dom.findall('//achievement'):
        # add completed achievements only:
        if not ach.get('dateCompleted'):
            continue

        if int(ach.get("id")) not in character.achievement_ids:
            #logging.info( "not seen achievement %s"%( ach.get("title") ))
            added.append(ach)
    
    logging.info("found %d achievments to add"%( len(added) ) )
    
    cached = Achievement.lookup_many_cached([ [x.get('id')] for x in added ])
    for ach in added:
        try:
            achievement = cached[ Achievement.key_name(ach.get("id")) ]
        except KeyError:
            pass
        if not achievement:
            logging.info("cache miss for Achievement [%s] %s"%(ach.get("id"), ach.get("title")))
            achievement = Achievement.find_or_create( ach.get('id'), ach.get('title'), ach.get('desc'), ach.get('icon') )
        character.achievement_ids.append( achievement.armory_id )
        character.achievement_dates.append( iso8601.parse_date(ach.get("dateCompleted")) )
    
    return len( added )



