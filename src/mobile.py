#! coding: utf-8
# pylint: disable-msg=W0311, W0611, E1103, E110

from raven.contrib.flask import Sentry
 
from flask import (Flask, request, 
                   render_template, render_template_string,
                   redirect, abort,
                   url_for, session, g, flash,
                   make_response, Response)
from flask_sslify import SSLify
from flask.ext.oauth import OAuth
from flask.ext.seasurf import SeaSurf
from flask.ext.assets import Bundle, Environment as WebAssets
from werkzeug.wrappers import Request, BaseRequest
from werkzeug.utils import cached_property
from werkzeug.contrib.securecookie import SecureCookie
from werkzeug.contrib.profiler import ProfilerMiddleware, MergeStream

from simplejson import dumps, loads

from jinja2 import Environment
from werkzeug.contrib.cache import MemcachedCache

import requests
import werkzeug.serving

import api
import settings
from app import CURRENT_APP


requests.adapters.DEFAULT_RETRIES = 3

app = CURRENT_APP
  
assets = WebAssets(app)

if settings.SENTRY_DSN:
  sentry = Sentry(app, dsn=settings.SENTRY_DSN, logging=False)
  
oauth = OAuth()



@app.route('/oauth/google', methods=['GET'])
def google_login():
  network = request.args.get('network', 'meta.jupo.com') 
  domain = request.args.get('domain', settings.PRIMARY_DOMAIN)
  utcoffset = request.args.get('utcoffset', 0)
  return redirect('https://accounts.google.com/o/oauth2/auth?response_type=code&scope=https://www.googleapis.com/auth/userinfo.email+https://www.googleapis.com/auth/userinfo.profile+https://www.google.com/m8/feeds/&redirect_uri=%s&state=%s&client_id=%s&hl=en&from_login=1&pli=1&prompt=select_account' \
                  % (settings.GOOGLE_MOBILE_APP_REDIRECT_URI, 
                     '%s|%s|%s' % (domain, network, utcoffset), 
                     settings.GOOGLE_CLIENT_ID))


@app.route('/oauth/google/authorized')
def google_authorized():
  code = request.args.get('code')
  __, network, utcoffset = request.args.get('state').split("|")
  
  # get access_token
  resp = requests.post('https://accounts.google.com/o/oauth2/token', 
                       data={'code': code,
                             'client_id': settings.GOOGLE_CLIENT_ID,
                             'client_secret': settings.GOOGLE_CLIENT_SECRET,
                             'redirect_uri': settings.GOOGLE_MOBILE_APP_REDIRECT_URI,
                             'grant_type': 'authorization_code'})
  data = loads(resp.text)
  token_type = data.get('token_type')
  access_token = data.get('access_token')
  
  # fetch user info
  resp = requests.get('https://www.googleapis.com/oauth2/v1/userinfo', 
                      headers={'Authorization': '%s %s' \
                               % (token_type, access_token)})
  user = loads(resp.text)
  if 'error' in user:   # Invalid Credentials
    abort(401, resp.text)
    

  url = 'https://www.google.com/m8/feeds/contacts/default/full/?max-results=1000'
  resp = requests.get(url, headers={'Authorization': '%s %s' \
                                    % (token_type, access_token)})
  
  contacts = api.re.findall("address='(.*?)'", resp.text)

  if contacts:
    contacts = list(set(contacts))  

  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))

  if not api.is_exists(db_name=db_name):
    api.new_network(db_name, db_name.split('_', 1)[0])
  
  session_id = api.sign_in_with_google(email=user.get('email'), 
                                       name=user.get('name'), 
                                       gender=user.get('gender'), 
                                       avatar=user.get('picture'), 
                                       link=user.get('link'), 
                                       locale=user.get('locale'), 
                                       verified=user.get('verified_email'),
                                       google_contacts=contacts,
                                       db_name=db_name)
  
  unread_notifications = api.get_unread_notifications_count(session_id,
                                                            db_name=db_name)
  session = SecureCookie({"session_id": session_id, 
                          "network": network,
                          "utcoffset": utcoffset}, 
                         settings.SECRET_KEY)
  
  # Get user info
  user_id = api.get_user_id(session_id, db_name=db_name)
  user = api.get_user_info(user_id, db_name=db_name)
  groups = []
  for group in api.get_groups(session_id, db_name=db_name, limit=5):
    groups.append({'name': group.name,
                   'link': 'http://%s/group/%s' \
                           % (settings.PRIMARY_DOMAIN, group.id)})
    
  data = {'id': user_id,
          'name': user.name,
          'avatar': user.avatar,
          'email': user.email,
          'groups': groups,
          'access_token': session.serialize(),
          'token_type': 'session',
          'unread_notifications': unread_notifications}
  
  return render_template('mobile/update_sidebar.html', data=dumps(data))



@app.route('/get_user_info')
def get_user_info():
  authorization = request.headers.get('Authorization')
  
  if not authorization or not authorization.startswith('session '):
    abort(401)
  
  session = SecureCookie.unserialize(authorization.split()[-1], 
                                     settings.SECRET_KEY)
  
  session_id = session.get('session_id')
  network = session.get('network')
  utcoffset = session.get('utcoffset')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  user_id = api.get_user_id(session_id, db_name=db_name)
  user = api.get_user_info(user_id, db_name=db_name)
  groups = []
  for group in api.get_groups(session_id, db_name=db_name):
    groups.append({'name': group.name,
                   'link': 'http://%s/group/%s' \
                           % (settings.PRIMARY_DOMAIN, group.id)})
    
  data = {'id': user.id,
          'name': user.name,
          'avatar': user.avatar,
          'email': user.email,
          'utcoffset': utcoffset,
          'groups': groups}
  
  resp = Response(dumps(data), mimetype='application/json')
  return resp

  
@app.route('/news_feed', methods=['GET'])
def news_feed(page=1):
  session_id = request.args.get('session_id')
  network = request.args.get('network')
  utcoffset = request.args.get('utcoffset')
  filter = request.args.get('filter', 'default')
  
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  view = 'news_feed'
  title = "Jupo"
  
  owner = api.get_owner_info(session_id, db_name=db_name)
  if not owner.id:
    return redirect_to('/oauth/google')
  
  feeds = api.get_feeds(session_id, page=page, 
                          include_archived_posts=False, db_name=db_name)
  
  
  pinned_posts = api.get_pinned_posts(session_id) \
                     if filter == 'default' else None
  
  
  
  suggested_friends = api.get_friend_suggestions(owner.to_dict())
  coworkers = api.get_coworkers(session_id)
  browser = api.Browser(request.headers.get('User-Agent'))
  category = None
  
  body = render_template('mobile/news_feed_mobile.html', 
                             owner=owner,
                             view=view, 
                             title=title, 
                             filter=filter,
                             browser=browser,
                             category=category,
                             coworkers=coworkers,
                             suggested_friends=suggested_friends,
                             pinned_posts=pinned_posts,
                             settings=settings,
                             feeds=feeds)
  
  return body


@app.route("/group/<int:group_id>", methods=["GET", "OPTIONS"])
def group(group_id=None, view='group', page=1):
  authorization = request.headers.get('Authorization')
  app.logger.debug(request.headers.items())
  
  if not authorization or not authorization.startswith('session '):
    abort(401)
  
  session = SecureCookie.unserialize(authorization.split()[-1], 
                                     settings.SECRET_KEY)
  
  session_id = session.get('session_id')
  network = session.get('network')
#   utcoffset = session.get('utcoffset')

  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)
  
  owner = api.get_user_info(user_id, db_name=db_name)
  group = api.get_group_info(session_id, group_id, db_name=db_name)
  if not group.id:
    abort(401)
    
  feeds = api.get_feeds(session_id, group_id,
                        page=page, db_name=db_name)
  
  return render_template('mobile/group.html', 
                          feeds=feeds, 
                          group=group,
                          owner=owner,
                          settings=settings,
                          view=view)
  
  
@app.route('/notifications', methods=['GET'])
def notifications():
  authorization = request.headers.get('Authorization')
  app.logger.debug(request.headers.items())
  
  if not authorization or not authorization.startswith('session '):
    abort(401)
  
  session = SecureCookie.unserialize(authorization.split()[-1], 
                                     settings.SECRET_KEY)
  
  session_id = session.get('session_id')
  network = session.get('network')
#   utcoffset = session.get('utcoffset')

  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))

  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)
    
  owner = api.get_user_info(user_id, db_name=db_name)
  
  notifications = api.get_notifications(session_id, db_name=db_name)
  
  
  return render_template('mobile/notifications.html',
                         owner=owner, 
                         network=network,
                         notifications=notifications)



if __name__ == "__main__":
  
  @werkzeug.serving.run_with_reloader
  def run_app(debug=True):
      
    from cherrypy import wsgiserver
      
    app.debug = debug
    
    server = wsgiserver.CherryPyWSGIServer(('0.0.0.0', 9000), app)
    try:
      print 'Serving HTTP on 0.0.0.0 port 9009...'
      server.start()
    except KeyboardInterrupt:
      print '\nGoodbye.'
      server.stop()
  
  
  run_app(debug=True)


