#! coding: utf-8
# pylint: disable-msg=W0311, W0611, E1103, E110

from raven.contrib.flask import Sentry
 
from flask import (Flask, request, 
                   render_template, render_template_string,
                   redirect as redirect_to, 
                   abort, 
                   url_for, session, g, flash,
                   make_response, Response)
from flask_sslify import SSLify
from flask.ext.oauth import OAuth
from flask.ext.seasurf import SeaSurf
from flask.ext.assets import Bundle, Environment as WebAssets
from werkzeug.wrappers import BaseRequest
from werkzeug.utils import cached_property
from werkzeug.contrib.securecookie import SecureCookie
from werkzeug.contrib.profiler import ProfilerMiddleware, MergeStream

from datetime import timedelta
from commands import getoutput
from mimetypes import guess_type
from simplejson import dumps, loads
from time import mktime, strptime, sleep
from urlparse import urlparse, urlunparse

from jinja2 import Environment
from werkzeug.contrib.cache import MemcachedCache

from lib import cache
from lib.img_utils import zoom
from lib.json_util import default as BSON

from helpers import extensions
from helpers.decorators import *
from helpers.converters import *

import os
import logging
import requests
import traceback
import werkzeug.serving
import flask_debugtoolbar
from flask_debugtoolbar_lineprofilerpanel.profile import line_profile

import api
import filters
import settings
from lib.verify_email_google import is_google_apps_email
from app import CURRENT_APP, render


requests.adapters.DEFAULT_RETRIES = 3

app = CURRENT_APP
  
assets = WebAssets(app)

if settings.SENTRY_DSN:
  sentry = Sentry(app, dsn=settings.SENTRY_DSN, logging=False)
  
csrf = SeaSurf(app)
oauth = OAuth()

@app.route('/oauth/google', methods=['GET'])
def google_login():
  domain = request.args.get('domain', settings.PRIMARY_DOMAIN)
  network = request.args.get('network', '') 
  return redirect('https://accounts.google.com/o/oauth2/auth?response_type=code&scope=https://www.googleapis.com/auth/userinfo.email+https://www.googleapis.com/auth/userinfo.profile+https://www.google.com/m8/feeds/&redirect_uri=%s&state=%s&client_id=%s&hl=en&from_login=1&pli=1&prompt=select_account' \
                  % (settings.GOOGLE_REDIRECT_URI, (domain + ";" + network), settings.GOOGLE_CLIENT_ID))


@app.route('/oauth/google/authorized')
def google_authorized():
  code = request.args.get('code')
  domain, network = request.args.get('state').split(";")
  # get access_token
  url = 'https://accounts.google.com/o/oauth2/token'
  resp = requests.post(url, data={'code': code,
                                  'client_id': settings.GOOGLE_CLIENT_ID,
                                  'client_secret': settings.GOOGLE_CLIENT_SECRET,
                                  'redirect_uri': settings.GOOGLE_REDIRECT_URI,
                                  'grant_type': 'authorization_code'})
  data = loads(resp.text)

  # save token for later use
  token = data.get('access_token')
  session['oauth_google_token'] = token
  
  # fetch user info
  url = 'https://www.googleapis.com/oauth2/v1/userinfo'
  resp = requests.get(url, headers={'Authorization': '%s %s' \
                                    % (data.get('token_type'),
                                       data.get('access_token'))})
  user = loads(resp.text)
  
  # generate user domain based on user email
  user_email = user.get('email')
  if not user_email or '@' not in user_email:
    return redirect('/oauth/google')
  
  user_domain = user_email.split('@')[1]

  if network and network != "":
    user_domain = network

  url = 'https://www.google.com/m8/feeds/contacts/default/full/?max-results=1000'
  resp = requests.get(url, headers={'Authorization': '%s %s' \
                                    % (data.get('token_type'),
                                       data.get('access_token'))})
  # get contact from Google Contacts, filter those that on the same domain (most likely your colleagues)
  contacts = api.re.findall("address='([^']*?@" + user_domain + ")'", resp.text)

  if contacts:
    contacts = list(set(contacts))  

  db_name = '%s_%s' % (user_domain.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))

  # create new network
  api.new_network(db_name, db_name.split('_', 1)[0])
  # sign in to this new network
  user_info = api.get_user_info(email=user_email, db_name=db_name)
  
  session_id = api.sign_in_with_google(email=user.get('email'), 
                                       name=user.get('name'), 
                                       gender=user.get('gender'), 
                                       avatar=user.get('picture'), 
                                       link=user.get('link'), 
                                       locale=user.get('locale'), 
                                       verified=user.get('verified_email'),
                                       google_contacts=contacts,
                                       db_name=db_name)
  
  app.logger.debug(db_name)
  app.logger.debug(user)
  app.logger.debug(session_id)
  
  api.update_session_id(user_email, session_id, db_name)
  session['session_id'] = session_id
  session.permanent = True
  groups = api.get_groups(session_id, db_name=db_name)
  list_info_group = []
  for group in groups:
    buffer = {}
    buffer['name'] = group.name
    buffer['link'] = 'http://%s/group/%s' % (settings.PRIMARY_DOMAIN,
                                                group.id) 
    list_info_group.append(buffer)
  
  
  unread_notification_count = api.get_unread_notifications_count(session_id,
                                                                 db_name=db_name)
  
  info_return = {'session_id': user_info.session_id,
                 'function_name': 'get_user_info',
                 'error': 0}
  
  print info_return
  
  resp = Response(render_template('mobile/template_push_mobile.html',
                                  info_push_to_mobile=dumps(info_return)))
  
  return resp

@app.route('/get_user_info', methods=['GET'])
def get_user_info():
  session_id = request.args.get('session_id')
  network = request.args.get('network')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  owner = api.get_owner_info(session_id, db_name=db_name)
  groups = api.get_groups(session_id, db_name=db_name)
  
  list_info_group = []
  for group in groups:
    buffer = {}
    buffer['name'] = group.name
    buffer['link'] = 'http://%s/group/%s' % (settings.PRIMARY_DOMAIN,
                                             group.id) 
    list_info_group.append(buffer)
  
  unread_notification_count = api.get_unread_notifications_count(session_id,
                                                                 db_name=db_name)
  
  
  info_return = {'_id': owner.id,
                 'name': owner.name,
                 'avatar': owner.avatar,
                 'session_id': owner.session_id,
                 'email': owner.email,
                 'groups': list_info_group,
                 'network': owner.email.split('@')[1],
                 'unread_notifications': unread_notification_count,
                 'function_name': 'get_user_info',
                 'error': 0}
  
  resp = Response(render_template('mobile/template_push_mobile.html',
                                  info_push_to_mobile=dumps(info_return)))
  
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
  session_id = request.args.get('session_id')
  network = request.args.get('network')
  utcoffset = request.args.get('utcoffset')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  owner = api.get_owner_info(session_id, db_name=db_name)
  if not owner.id:
    return redirect_to('/oauth/google')
  
  group = api.get_group_info(session_id, group_id, db_name=db_name)
  feeds = api.get_feeds(session_id, group_id,
                        page=page, db_name=db_name)
    
  body = render_template('mobile/group_mobile.html', 
                          feeds=feeds, 
                          group=group,
                          owner=owner,
                          settings=settings,
                          view=view)
        
  return body
  
  
  
@app.route('/notifications', methods=['GET'])
def notifications():
  session_id = request.args.get('session_id')
  network = request.args.get('network')
  utcoffset = request.args.get('utcoffset')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))

  owner = api.get_owner_info(session_id, db_name=db_name)
  if not owner.id:
    return redirect_to('/oauth/google')
  
  notifications = api.get_notifications(session_id, db_name=db_name)
  unread_messages = api.get_unread_messages(session_id, db_name=db_name)
  unread_messages_count = len(unread_messages)
  
  
  body = render_template('mobile/notifications_mobile.html',
                           owner=owner, 
                           network=network,
                           unread_messages=unread_messages,
                           notifications=notifications)
  
  return body



#===============================================================================
# Run App
#===============================================================================
from werkzeug.wrappers import Request

class NetworkNameDispatcher(object):
  """
  Convert the first part of request PATH_INFO to hostname for backward 
  compatibility
  
  Eg: 
    
     http://jupo.com/example.com/news_feed
     
  -> http://example.com.jupo.com/news_feed
  
   
  """
  def __init__(self, app):
    self.app = app

  def __call__(self, environ, start_response):
    path = environ.get('PATH_INFO', '')
    items = path.lstrip('/').split('/', 1)
    
    if '.' in items[0] and api.is_domain_name(items[0]):  # is domain name
      # print "DEBUG - in NetworkNameDispatcher - items = " + items[0]
      
      # save user network for later use
      # session['subnetwork'] = items[0]

      environ['HTTP_HOST'] = items[0] + '.' + settings.PRIMARY_DOMAIN
      if len(items) > 1:
        environ['PATH_INFO'] = '/%s' % items[1]
      else:
        environ['PATH_INFO'] = '/'
      
      return self.app(environ, start_response)
        
    else:
      request = Request(environ)
      network = request.cookies.get('network')
      if not network:
        return self.app(environ, start_response)
      
      if request.method == 'GET':
        url = 'http://%s/%s%s' % (settings.PRIMARY_DOMAIN,
                                  network, request.path)
        if request.query_string:
          url += '?' + request.query_string
          
        response = redirect(url)
        return response(environ, start_response)
      
      else:
        environ['HTTP_HOST'] = network + '.' + settings.PRIMARY_DOMAIN
        return self.app(environ, start_response)
        
      
    

app.wsgi_app = NetworkNameDispatcher(app.wsgi_app)



if __name__ == "__main__":
  
  @werkzeug.serving.run_with_reloader
  def run_app(debug=True):
      
    from cherrypy import wsgiserver
      
    app.debug = debug
  
    # app.config['SERVER_NAME'] = settings.PRIMARY_DOMAIN
    
    app.config['DEBUG_TB_PROFILER_ENABLED'] = True
    app.config['DEBUG_TB_TEMPLATE_EDITOR_ENABLED'] = True
    app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
    app.config['DEBUG_TB_PANELS'] = [
        'flask_debugtoolbar.panels.versions.VersionDebugPanel',
        'flask_debugtoolbar.panels.timer.TimerDebugPanel',
        'flask_debugtoolbar.panels.headers.HeaderDebugPanel',
        'flask_debugtoolbar.panels.request_vars.RequestVarsDebugPanel',
        'flask_debugtoolbar.panels.template.TemplateDebugPanel',
        'flask_debugtoolbar.panels.logger.LoggingPanel',
        'flask_debugtoolbar_mongo.panel.MongoDebugPanel',
        'flask_debugtoolbar.panels.profiler.ProfilerDebugPanel',
        'flask_debugtoolbar_lineprofilerpanel.panels.LineProfilerPanel'
    ]
    app.config['DEBUG_TB_MONGO'] = {
      'SHOW_STACKTRACES': True,
      'HIDE_FLASK_FROM_STACKTRACES': True
    }
    
  #   toolbar = flask_debugtoolbar.DebugToolbarExtension(app)
    
  
    
    server = wsgiserver.CherryPyWSGIServer(('0.0.0.0', 9000), app)
    try:
      print 'Serving HTTP on 0.0.0.0 port 9000...'
      server.start()
    except KeyboardInterrupt:
      print '\nGoodbye.'
      server.stop()
  
  
  run_app(debug=True)


