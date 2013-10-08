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

@app.route('/oauth/google', methods=['POST', 'GET', 'OPTIONS'])
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
    return redirect('/')
  
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
  
  info_return = {'_id': user_info.id,
                 'name': user_info.name,
                 'avatar': user_info.avatar,
                 'session_id': user_info.session_id,
                 'error': 0}
  
  resp = Response(render_template('template_push_mobile.html',
                                  type_push_mobile='login_google',
                                  url_push_to_mobile=dumps(info_return)))
  
  return resp


@app.route("/news_feed", methods=["GET"])
def news_feed():
  session_id = request.args.get('session_id')
  network = request.args.get('network')
  utcoffset = request.args.get('utcoffset')
  
  
  unread_notification_count = api.get_unread_notifications_count(session_id)
  info_return = {'error': 0, 'count': unread_notification_count}
  resp = Response(render_template('template_push_mobile.html',
                                  type_push_mobile='news_feed',
                                  url_push_to_mobile=dumps(info_return)))

  return resp

@app.route('/notifications', methods=['GET'])
def notifications():
  session_id = request.args.get('session_id')
  network = request.args.get('network')
  utcoffset = request.args.get('utcoffset')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))

  notifications = api.get_notifications(session_id, db_name=db_name)
  unread_messages = api.get_unread_messages(session_id, db_name=db_name)
  unread_messages_count = len(unread_messages)
  
  owner = api.get_owner_info(session_id, db_name=db_name)
  body = render_template('mobile/notifications_mobile.html',
                           owner=owner, 
                           network=network,
                           unread_messages=unread_messages,
                           notifications=notifications)
  
  return body
  
  
@app.route("/news_feed1", methods=["GET", "OPTIONS"])
@line_profile
def news_feed1():
  session_id = session.get("session_id")
  unread_notification_count = api.get_unread_notifications_count(session_id)
  info_return = {'error': 0, 'count': unread_notification_count}
  resp = Response(render_template('news_feed_mobile.html'))
  return resp




@app.route("/", methods=["GET"])
@line_profile
def home():
  hostname = request.headers.get('Host', '').split(':')[0]
  print "DEBUG - in home() - hostname = " + str(hostname)
  
  session_id = request.args.get('session_id')
  
  network = ""
  network_exist = 1

  if hostname != settings.PRIMARY_DOMAIN:
    # used to 404 if network doesn't exist. now we switch to customized landing page for them (even if network doesn't exist yet)
    if not api.is_exists(db_name=hostname.replace('.', '_')):
      network_exist = 0
    network = hostname[:(len(hostname) - len(settings.PRIMARY_DOMAIN) - 1)]

    if session_id:
      session.permanent = True
      session['session_id'] = request.args.get('session_id')

      return redirect('/news_feed')
  
  session_id = session.get("session_id")
  user_id = api.get_user_id(session_id)

  if not user_id:
    code = request.args.get('code')
    user_id = api.get_user_id(code)
    
    if code and not user_id:
      flash('Invitation is invalid. Please check again')
      return redirect('http://' + settings.PRIMARY_DOMAIN)

    if user_id and not session_id:
      session['session_id'] = code
      owner = api.get_user_info(user_id)

      resp = make_response(
               render_template('profile_setup.html',
                                 owner=owner, jupo_home=settings.PRIMARY_DOMAIN,
                                 code=code, user_id=user_id)
             )

      # set the network here so that api.get_database_name() knows which network calls it
      resp.set_cookie('network', owner.email_domain)

      return resp


  
  if not session_id or not user_id:
    try:
      session.pop('session_id')
    except KeyError:
      pass
    
#     if hostname != settings.PRIMARY_DOMAIN:
#       return redirect('/sign_in')
    
    email = request.args.get('email')
    message = request.args.get('message')
    resp = Response(render_template('landing_page.html',
                                    email=email,
                                    settings=settings,
                                    domain=settings.PRIMARY_DOMAIN,
                                    network=network,
                                    network_exist=network_exist,
                                    message=message))
    
    back_to = request.args.get('back_to')
    if back_to:
      resp.set_cookie('redirect_to', back_to)
    
    return resp
  else:
    return redirect('http://%s/%s/news_feed' % (settings.PRIMARY_DOMAIN,
                                                request.cookies.get('network')))






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
