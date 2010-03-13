from google.appengine.ext import db
from google.appengine.api import memcache

from utils import slugify
import logging
from datetime import datetime
import urllib
import yaml

class BaseModel(db.Model):
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)

    @classmethod
    def key_name(cls, *args):
        return ":".join( [ cls.__name__ ] + [ slugify(unicode(a).strip().lower()) for a in args ])
    
    @classmethod
    def lookup(cls, *args):
        # NOTE - I'm assuming that slugify(slugify(x)) == slugify(x) here, because I pass urltokens in for these sometimes
        return cls.get_by_key_name( cls.key_name(*args) )
    
    @classmethod
    def lookup_cached( cls, *args ):
        key_name = cls.key_name(*args)
        cached = memcache.get( key_name )
        if cached:
            logging.debug("using cached %s [%s]"%(cls, repr(args)))
            return cached
        logging.debug("not cached %s [%s]"%(cls, repr(args)))
        instance = cls.lookup( *args )
        memcache.set( key_name, instance )
        return instance
    
    @classmethod
    def lookup_many_cached(cls, ids):
        keys = []
        for args in ids:
            keys.append( cls.key_name( *args ) )
        found = memcache.get_multi( keys )
        missing = []
        for key in keys:
            if key not in found:
                missing.append(key)
        logging.info("%d objects not cached - fetching"%( len(missing) ))
        fetched = cls.get_by_key_name(missing)
        added = {}
        for key, instance in zip( missing, fetched ):
            found[key] = instance
            added[key] = found[key]
        
        if added.keys():
            memcache.add_multi( added )
        return found

    def timeago(self):
        if not self.last_fetch: return None
        return self.last_fetch.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        
    def put(self):
        memcache.delete( self.key().name() )
        return super( BaseModel, self ).put()
    
class Guild(BaseModel):
    owner = db.UserProperty()

    continent = db.StringProperty()
    realm = db.StringProperty()
    realm_urltoken = db.StringProperty()
    name = db.StringProperty()
    urltoken = db.StringProperty()

    last_fetch = db.DateTimeProperty()
    fetch_error = db.StringProperty()
    
    weekly_email_last = db.DateTimeProperty()
    weekly_email_address = db.StringProperty()
    
    achievements_cache = db.TextProperty()
    
    @classmethod
    def find_or_create(cls, continent, realm, name):
        continent = continent.lower()
        if not continent in [ u'us', u'eu' ]:
            continent = u'us'
            
        if not (name.strip() and realm.strip()):
            return None
        
        key_name = cls.key_name( continent, realm, name )
        
        g = cls.get_by_key_name( key_name )
        if g:
            return g
        g = Guild( key_name = key_name, continent = continent, realm = realm, name = name )
        g.urltoken = slugify(g.name)
        g.realm_urltoken = slugify(g.realm)
        return g

    def url(self):
        return "/%s/%s/guild/%s/"%( self.continent, self.realm_urltoken, self.urltoken )
        
    def server(self):
        if self.continent == 'eu':
            return "eu.wowarmory.com"
        else:
            return "www.wowarmory.com"
    
    def oldest_fetch(self):
        try:
            return self._oldest_fetch
        except AttributeError:
            if not self.character_set:
                self._oldest_fetch = None
            self._oldest_fetch = self.character_set.order("last_fetch").fetch(1)[0]
        return self._oldest_fetch
    
    def armory_url(self):
        return "http://%s/guild-info.xml?r=%s&n=%s&p=1"%( self.server(), urllib.quote(self.realm.encode('utf-8'),''), urllib.quote(self.name.encode('utf-8'),'') )
    
    def set_achievements_cache( self, obj ):
        self.achievements_cache = yaml.dump( obj )

    def get_achievements_cache( self ):
        if self.achievements_cache:
            return yaml.load( self.achievements_cache )
        return {}
    
    def update_achievements_cache_for( self, character ):
        cache = self.get_achievements_cache()
        cache[ character.name ] = {
            "name":character.name,
            "url":character.url,
            "ids":character.achievement_ids,
            "dates":character.achievement_dates,
        }
        self.set_achievements_cache( cache )
    
    def remove_character_from_cache( self, character ):
        cache = self.get_achievements_cache()
        del cache[ character.name ]
        self.set_achievements_cache( cache )
        


class Character(BaseModel):

    last_fetch = db.DateTimeProperty()
    
    continent = db.StringProperty()
    realm = db.StringProperty()
    realm_urltoken = db.StringProperty()

    guild = db.ReferenceProperty( Guild )

    name = db.StringProperty()
    urltoken = db.StringProperty()

    raceId = db.IntegerProperty()
    classId = db.IntegerProperty()
    level = db.IntegerProperty()
    rank = db.IntegerProperty()
    
    achPoints = db.IntegerProperty()
    
    achievement_ids = db.ListProperty( long )
    achievement_dates = db.ListProperty( datetime )
    
    @classmethod
    def find_or_create(cls, continent, realm, name):
        key_name = cls.key_name( continent, realm, name )
        c = cls.get_by_key_name( key_name )
        if c:
            return c
        c = Character( key_name = key_name, continent = continent, realm = realm, name = name )
        c.urltoken = slugify(name)
        c.realm_urltoken = slugify(realm)
        return c

    def raceName(self):
        if self.raceId:
            return {
                2:"Orc",
                5:"Undead",
                6:"Tauren",
                8:"Troll",
                10:"Blood Elf",
            }[ self.raceId ]
        return None
    
    def className(self):
        if self.classId:
            return {
                1:"Warrior",
                2:"Paladin",
                3:"Hunter",
                4:"Rogue",
                5:"Priest",
                6:"Death Knight",
                7:"Shaman",
                8:"Mage",
                9:"Warlock",
                11:"Druid",
            }[ self.classId ]
        return None

    def url(self):
        return "/%s/%s/character/%s/"%( self.continent, self.realm_urltoken, self.urltoken )
    
    def server(self):
        if self.continent == 'eu':
            return "eu.wowarmory.com"
        else:
            return "www.wowarmory.com"

    def armory_url(self):
        return "http://%s/character-achievements.xml?r=%s&n=%s"%( self.server(), urllib.quote(self.realm.encode('utf-8'),''), urllib.quote( self.name.encode('utf-8'),'') )


class Achievement(BaseModel):

    armory_id = db.IntegerProperty()
    name = db.StringProperty()
    description = db.StringProperty()
    image = db.StringProperty()
    
    @classmethod 
    def find_or_create(cls, armory_id, name, description, icon):
        key_name = cls.key_name( armory_id )

        instance = cls.get_by_key_name( key_name )
        if not instance:
            instance = Achievement( key_name = key_name )
            instance.armory_id = long(armory_id)
            instance.name = name
            instance.description = description
            instance.image = "http://www.wowarmory.com/wow-icons/_images/51x51/%s.jpg"%( icon )
            instance.put() # TODO - dirty flag

        memcache.set( key_name, instance )
        
        return instance
    
    def url(self, guild):
        return guild.url() + "achievement/%s/"%( self.armory_id )
    
    def wowhead_url(self):
        return "http://www.wowhead.com/?achievement=%s"%( self.armory_id )
        