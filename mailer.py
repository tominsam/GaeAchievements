from google.appengine.api import mail
from datetime import datetime, timedelta
import logging
import itertools
import re

from model import *
from google.appengine.api.labs import taskqueue

from jinja2 import Environment, FileSystemLoader

def weekly_summaries():
    # call this method on mondays. It can cope with being called more than
    # once on a monday, but don't call it all the time.

    guilds = Guild.all().filter( "weekly_email_last", None ).fetch(100)
    if len(guilds) < 100:
        guilds += Guild.all().filter( "weekly_email_last <",  datetime.utcnow() - timedelta( days = 2 ) )

    queue = taskqueue.Queue( name = "mailer" )
    for guild in guilds:
        if guild.weekly_email_address:
            logging.info("queueing mail for %s/%s/%s to %s"%( guild.continent, guild.realm, guild.name, guild.weekly_email_address ))
            task = taskqueue.Task( url='/queue/mailer/', params={'key': str(guild.key())} )

def send_weekly_summary( guild, email = None, request = None ):
    if not email:
        email = guild.weekly_email_address

    if not email:
        raise Exception("no email address for guild %s/%s/%s"%( guild.continent, guild.realm, guild.name ))

    logging.info("sending mail for guild %s/%s/%s"%( guild.continent, guild.realm, guild.name ))

    start = datetime.utcnow() - timedelta( days = 7 )

    achievement_data = guild.unified_achievement_list()
    achievement_data = filter(lambda d: d['date'].isoformat() >= start.isoformat(), achievement_data)

    # TODO - this is cloned from web_handler
    lookup_ids = []
    for a in achievement_data:
        lookup_ids.append( [ a['achievement_id'] ] )
    looked_up = Achievement.lookup_many_cached( lookup_ids )
    for a in achievement_data:
        a["achievement"] = looked_up[ Achievement.key_name(a['achievement_id']) ]

    # TODO - fetch all at once!
    for a in achievement_data:
        a['character'] = Character.get( a['character_key'] )
    
    achievement_data.sort(lambda a, b: cmp(a['character_name'], b['character_name']) ) # have to sort before grouping
    people = {}
    for data in achievement_data:
        character = data['character']
        if character:
            if not character.name in people:
                people[ character.name ] = [ data['character'], [] ]
            people[ character.name ][1].append( data )

    people = people.values()
    people.sort(lambda a,b: cmp( b[0].achPoints, a[0].achPoints ) )

    level_80 = guild.character_set.filter( "level", 80 ).count()
    total = guild.character_set.count()

    levels = filter(lambda d: re.search(r'Level \d', d['achievement'].name), achievement_data )
    levels = map(lambda d: [ d['character'], int( re.search(r'Level (\d+)', d["achievement"].name).group(1) ) ], levels)
    levels.sort(lambda a, b: cmp(b[1], a[1])) # sort by level, reversed

    jinja2_env = Environment(
        loader=FileSystemLoader('templates'),
        line_statement_prefix="#",
        autoescape=True
    )

    if request:
        root = "http://%s"%( request.host )
    else:
        root = "http://dummy"

    logging.info("root is %s"%root)
    template = jinja2_env.get_template("email_text.html")
    body = template.render( locals() )

    template = jinja2_env.get_template("email_html.html")
    html = template.render( locals() )

    # save guild first so that failure case is that we don't send mail,
    # rather than sending lots of mail
    guild.weekly_email_last = datetime.utcnow()
    guild.put()

    mail.send_mail(
        sender="Tom's Magical Mail Sending Robot <tom.insam@gmail.com>",
        to=email,
        subject="The magical world of %s, week beginning %s"%( guild.name, start.strftime("%d %B") ),
        body=body,
        html=html
    )

