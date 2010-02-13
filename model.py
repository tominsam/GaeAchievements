from google.appengine.ext import db
from google.appengine.api import memcache

from utils import slugify
import logging
from datetime import datetime
import urllib

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
            logging.info("using cached %s [%s]"%(cls, repr(args)))
            return cached
        logging.info("not cached %s [%s]"%(cls, repr(args)))
        instance = cls.lookup( *args )
        memcache.add( key_name, instance )
        return instance

    def timeago(self):
        if not self.last_fetch: return None
        return self.last_fetch.strftime("%Y-%m-%dT%H:%M:%S+00:00")


class Guild(BaseModel):
    owner = db.UserProperty()

    continent = db.StringProperty()
    realm = db.StringProperty()
    realm_urltoken = db.StringProperty()
    name = db.StringProperty()
    urltoken = db.StringProperty()

    last_fetch = db.DateTimeProperty()
    fetch_error = db.StringProperty()
    
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
        if not self.character_set: return None
        return self.character_set.order("last_fetch")[0]
    
    def character_count(self):
        return self.character_set.count()

    def fetch_count(self):
        return self.character_set.filter("last_fetch !=", None ).count()

    def armory_url(self):
        return "http://%s/guild-info.xml?r=%s&n=%s&p=1"%( self.server(), urllib.quote(self.realm.encode('utf-8'),''), urllib.quote(self.name.encode('utf-8'),'') )


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
        
        return instance
    
    def url(self, guild):
        return guild.url() + "achievement/%s/"%( self.armory_id )
    
    def wowhead_url(self):
        return "http://www.wowhead.com/?achievement=%s"%( self.armory_id )
        