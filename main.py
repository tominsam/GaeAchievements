from google.appengine.ext import webapp
from google.appengine.ext.webapp import util

from web_handler import *
from queue_handler import *
from cron_handler import *

def main():
    application = webapp.WSGIApplication([
        ('/', RootHandler),
        (r'/(\w{2})/(.*?)/guild/(.*?)/achievement/(.*?)/', GuildAchievementHandler),
        (r'/(\w{2})/(.*?)/guild/(.*?)/members/', GuildMembersHandler),
        (r'/(\w{2})/(.*?)/guild/(.*?)/feed/', GuildFeedHandler),
        (r'/(\w{2})/(.*?)/guild/(.*?)/', GuildMainHandler),
        (r'/(\w{2})/(.*?)/character/(.*?)/', CharacterHandler),
        ('/fetcher/guild/', GuildFetcher),
        ('/fetcher/character/', CharacterFetcher),
        ('/queue/mailer/', GuildMailer),
        ('/cron/hourly/', HourlyCron),
        ('/cron/weekly/', WeeklyCron),
        ('.*', NotFound),
        
    ], debug=True)
    util.run_wsgi_app(application)
if __name__ == '__main__':
    main()

