#! coding: utf-8
# pylint: disable-msg=W0311, W0611, E1103, E1101
#@PydevCodeAnalysisIgnore

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
from app import CURRENT_APP, render


requests.adapters.DEFAULT_RETRIES = 3

app = CURRENT_APP
  
assets = WebAssets(app)

if settings.SENTRY_DSN:
  sentry = Sentry(app, dsn=settings.SENTRY_DSN, logging=False)
csrf = SeaSurf(app)
oauth = OAuth()

@line_profile
def render_homepage(session_id, title, **kwargs):  
  """ Render homepage for signed in user """
  if session_id:
    user_id = api.get_user_id(session_id)
    if user_id:
      owner = api.get_user_info(user_id)
    else:
      owner = None
  else:
    owner = None
    
  if owner:
    friends_online = [i for i in owner.contact_ids \
                      if api.check_status(i) in ['online', 'away']]
    friends_online = [api.get_user_info(i) for i in friends_online]
    friends_online.sort(key=lambda k: k.last_online, reverse=True)
    if not kwargs.has_key('groups'):
      groups = api.get_groups(session_id, limit=3)
    else:
      groups = kwargs.pop('groups')
    
    for group in groups[:3]:
      group.unread_posts = 0 # api.get_unread_posts_count(session_id, group.id)
    
    unread_messages = api.get_unread_messages(session_id)
#     unread_messages_count = sum([i.get('unread_count') for i in unread_messages])
    unread_messages_count = len(unread_messages)
    unread_notification_count = api.get_unread_notifications_count(session_id)\
                              + unread_messages_count
    
  else:
    friends_online = []
    groups = []
    unread_messages = []
    unread_messages_count = 0
    unread_notification_count = 0
  
  if kwargs.has_key('stats'):  
    stats = kwargs.pop('stats')
  else: 
    stats = {}
    
  
  hostname = request.headers.get('Host')
  logo_text = 'Jupo'
  if hostname != settings.PRIMARY_DOMAIN:
    network_info = api.get_network_info(hostname.replace('.', '_'))
    if network_info and network_info.has_key('name'):
      logo_text = network_info['name']
      if title == 'Jupo':
        title = logo_text

  resp = Response(render_template('home.html', 
                                  owner=owner,
                                  title=title, 
                                  groups=groups,
                                  friends_online=friends_online,
                                  unread_messages=unread_messages,
                                  unread_messages_count=unread_messages_count,
                                  unread_notification_count=unread_notification_count,
                                  stats=stats,
                                  debug=settings.DEBUG,
                                  logo_text=logo_text,
                                  domain=hostname,
                                  request=request,
                                  **kwargs))
  if owner:
    resp.set_cookie('channel_id', api.get_channel_id(session_id))
  else:
    resp.delete_cookie('channel_id')
  
  # disallows rendering of the document when inside an iframe
  # http://javascript.info/tutorial/clickjacking
  resp.headers['X-Frame-Options'] = 'DENY'
  return resp


def event_stream(channel):
  pubsub = api.PUBSUB.pubsub()
  pubsub.subscribe(channel)
  for message in pubsub.listen():
    yield 'retry: 1000\ndata: %s\n\n' % message['data']
    
#===============================================================================
# URL routing and handlers
#===============================================================================
@app.route('/ping')
def ping():
  session_id = session.get('session_id')
  if session_id:
    api.update_pingpong_timestamp(session_id)
  return 'pong'

@app.route('/stream')
def stream():
  session_id = session.get('session_id')
  if not session_id:
    abort(400)
    
  # Update utcoffset
  user_id = api.get_user_id(session_id)
  if user_id:
    utcoffset = request.cookies.get('utcoffset')
    if utcoffset:
      api.update_utcoffset(user_id, utcoffset)
  
  channel_id = request.cookies.get('channel_id')
  resp = Response(event_stream(channel_id),
                  mimetype="text/event-stream")
  resp.headers['X-Accel-Buffering'] = 'no'
#   resp.headers['Access-Control-Allow-Origin'] = '*'
  return resp


@csrf.exempt
@app.route("/autocomplete")
@line_profile
def autocomplete():
  session_id = session.get("session_id")
  query = request.args.get('query')
  type = request.args.get('type')
    
  if not query: # preload all groups & coworkers
    owners = api.get_contacts(session_id)
    user_ids = [i.id for i in owners]
    for user in api.get_all_users():
      if user.id not in user_ids:
        user_ids.append(user.id)
        owners.append(user)
    
    if type != 'user':
      groups = api.get_groups(session_id)
      group_ids = [i.id for i in groups]
      owners.extend(groups)
  
      items = [{'id': 'public', 
                'name': 'Public',
                'avatar': '/public/images/public-group.png',
                'type': 'group'}]
      
      for group in api.get_all_groups():
        if group.id not in group_ids:
          group_ids.append(group.id)
          owners.append(group)
      
    else:
      items = []
      
    for i in owners:
      if i.is_group():
        info = {'name': i.name, 
                'id': str(i.id), 
                'avatar': '/public/images/group-icon2.png',
                'type': 'group'}
        items.append(info)
      else:          
        names = [i.name]  
        for name in names:
          info = {'name': name, 
                  'id': str(i.id), 
                  'avatar': i.avatar,
                  'type': 'user'}
          
          items.append(info)  
          
      
  else:
      
    if type == 'user': # mentions
      _items = api.autocomplete(session_id, query)
      items = []
      for item in _items:
        if not api.is_group(item.get('id')):  # only show user, not group
          info = api.get_user_info(item.get('id'))
          avatar = info.avatar
          type = 'user'
        
          items.append({'id': str(item.get('id')),
                        'name': item.get('name', item.get('email')),
                        'avatar': avatar,
                        'type': type})
    else:
      _items = api.autocomplete(session_id, query)
      items = []
      for item in _items:
        info = api.get_owner_info_from_uuid(item.get('id'))
        avatar = '/public/images/group.png' if info.is_group() else info.avatar
      
        items.append({'id': str(item.get('id')),
                      'name': item.get('name', item.get('email')),
                      'avatar': avatar,
                      'type': item.get('type')})
      
  return dumps(items)



@app.route("/search", methods=['GET', 'OPTIONS', 'POST'])
@login_required
@line_profile
def search():
  t0 = api.utctime()

  session_id = session.get("session_id")
  query = request.form.get('query', request.args.get('query', '')).strip()
  item_type = request.args.get('type')
  page = int(request.args.get('page', 1))
  ref_user_id = request.args.get('user')
  
  ref = request.args.get('ref')
  if ref and 'group-' in ref:
    group_id = ref.split('-')[1]
    group = api.get_group_info(session_id, group_id)
    if item_type == 'people':
      title = 'Add people to group'
    else:
      title = 'Invite your friends'
  elif ref == 'everyone':
    title = 'Invite your friends'
    group_id = group = None
  else:
    group_id = group = None
    title = 'Add Contacts'
  
  user_id = api.get_user_id(session_id)
  owner = api.get_user_info(user_id)
  if ref_user_id:
    user = api.get_user_info(ref_user_id)
  else:
    user = None
    
  if item_type in ['people', 'email']: 
      
    if request.method == 'OPTIONS':
      if query:
        if item_type == 'people':
          users = api.people_search(query, group_id)
          if users:
            users = [i for i in users \
                     if i.id not in owner.contact_ids and i.id != owner.id]
          else:
            users = [i for i in api.get_coworkers(session_id) \
                     if i.id not in group.member_ids and i.id != owner.id]
        else:
          users = [i for i in owner.google_contacts \
                   if api.get_user_id_from_email_address(i.email) not in group.member_ids]
          
      elif group_id:
        if item_type == 'email':
          users = [i for i in owner.google_contacts \
                   if api.get_user_id_from_email_address(i.email) not in group.member_ids]
        else:
          users = owner.contacts
          user_ids = [i.id for i in users]
          for user in api.get_coworkers(session_id):
            if user.id not in user_ids:
              user_ids.append(user.id)
              users.append(user)
              
          users = [i for i in users \
                   if i.id not in group.member_ids and i.id != owner.id]
      else:
        if item_type == 'email':
          users = [i for i in owner.google_contacts]
        else:
          users = owner.contacts
          user_ids = [i.id for i in users]
          for user in api.get_coworkers(session_id):
            if user.id not in user_ids:
              user_ids.append(user.id)
              users.append(user)
          users = [i for i in users \
                   if i.id not in owner.contact_ids and i.id != owner.id]
          
      return dumps({'title': title,
                    'body': render_template('people_search.html',
                                            title=title, 
                                            mode='search',
                                            type=item_type,
                                            group_id=group_id,
                                            group=group,
                                            users=users,
                                            query=query, 
                                            owner=owner)})
    else:
      if item_type == 'people':
        users = api.people_search(query)
      else:
        q = query.lower()
        users = [i for i in owner.google_contacts \
                 if i.email and i.email.lower().startswith(q)]
        
          
      if group_id:
        out = [i for i in users if i.email and i.id not in group.member_ids and i.id != owner.id]
        out.extend([i for i in users if i.email and i.id != owner.id and i.id in group.member_ids])
        users = out
      else:
        users = [i for i in users if i.email]
      
        
      if users:
        return ''.join(render_template('user.html', 
                                       mode='search', 
                                       user=user, 
                                       group_id=group_id,
                                       group=group,
                                       type=item_type,
                                       query=query,
                                       owner=owner,
                                       title=title) \
                       for user in users if user.email)
      else:
        return "<li>Type your friend's email address</li>"
#         if item_type == 'email':
#           return "<li>Type your friend's email address</li>"
#         else:
#           return "<li>0 results found</li>"
        
  # search posts
  results = api.search(session_id, query, item_type, 
                       ref_user_id=ref_user_id, page=page)
  if results and results.has_key('counters'):
    hits = results.get('hits', 0)
    total = sum([i['count'] for i in results.get('counters')])
    counters = results['counters']
  else:
    hits = 0
    total = 0
    counters = {}
    
  due = api.utctime() - t0
#   owner = api.get_owner_info(session_id)
  coworkers = api.get_coworkers(session_id)
  
  if request.method == 'GET':
    return render_homepage(session_id, 'Results for "%s"' % query,
                           query=query, 
                           type=item_type,
                           due='%.3f' % due,
                           total=total,
                           hits=hits,
                           coworkers=coworkers,
                           user=user,
                           view='results',
                           page=page,
                           counters=counters)

    
  if page == 1:
    body = render_template('results.html', owner=owner,
                                           query=query, 
                                           type=item_type,
                                           due='%.3f' % due,
                                           total=total,
                                           hits=hits,
                                           coworkers=coworkers,
                                           user=user,
                                           view='results',
                                           page=page,
                                           counters=counters)
  else:
    posts = [render(hits, "feed", owner, 'results')]
      
    if len(hits) == 0:
      posts.append(render_template('more.html', more_url=None))
    else:
      more_url = '/search?query=%s&page=%s' % (query, page+1)
      if item_type:
        more_url += '&type=%s' % item_type
      if user:
        more_url += '&user=%s' % user
       
      posts.append(render_template('more.html', more_url=more_url))
    return ''.join(posts)
  
  # TODO: render 1 lần thôi :(
  if body.split('<ul id="stream">')[-1].split('<script>')[0].split('right-sidebar')[0].count(query) < 2:
    spelling_suggestion = api.get_spelling_suggestion(query)
    app.logger.debug('spelling suggestion: %s' % spelling_suggestion)
    body = render_template('results.html', owner=owner,
                                           spelling_suggestion=spelling_suggestion,
                                           query=query, 
                                           type=item_type,
                                           due='%.3f' % due,
                                           total=total,
                                           hits=hits,
                                           coworkers=coworkers,
                                           user=user,
                                           view='results',
                                           counters=counters)
    
  json = dumps({'title': '%s - Jupo Search' % query,
                'body': body})
  return Response(json, content_type='application/json')


#@app.route("/", methods=["GET", "OPTIONS"])
@app.route('/<any(discover, starred, hot, incoming, shared_by_me):name>', methods=['GET', 'OPTIONS'])
@app.route('/<any(discover, starred, hot, incoming, shared_by_me):name>/page<int:page>', methods=['OPTIONS'])
def discover(name='discover', page=1):
  code = request.args.get('code')
  user_id = api.get_user_id(code)
  if user_id:
    session['session_id'] = code
    return render_homepage(code, 'Complete Profile',
                           code=code, user_id=user_id)
    
  session_id = session.get("session_id")
  
  
  app.logger.debug('session_id: %s' % session_id)
  
  user_id = api.get_user_id(session_id)
  
  if user_id:
    owner = api.get_user_info(user_id)
    if name == 'starred':
      category = name
      feeds = api.get_starred_posts(session_id, page=page)
    elif name == 'hot':
      category = name
      feeds = api.get_hot_posts(page=page)
    elif name == 'shared_by_me':
      category = name
      feeds = api.get_shared_by_me_posts(session_id, page=page)
    elif request.path in ['/', '/incoming', '/discover']:
#      feeds = api.get_incoming_posts(session_id, page=page)
      feeds = api.get_discover_posts(session_id, page=page)
#      feeds = api.get_public_posts(session_id=session_id, page=page)
      category = None     
    else:
      feeds = api.get_public_posts(session_id=session_id, page=page)
      category = None     
  else:
    feeds = api.get_public_posts(session_id=session_id, page=page)
    owner = category = None     
    if session.has_key('session_id'):
      session.pop('session_id')
  
  public_groups = api.get_open_groups(limit=10) 


  if request.method == 'OPTIONS':  
    if page == 1:
      menu = render_template('menu.html', 
                             owner=owner,
                             category=category,
                             view='discover')
        
      body = render_template('discover.html', 
                             view='discover', 
                             category=category,
                             public_groups=public_groups,
                             owner=owner,
                             title='Discover', 
                             feeds=feeds)
      
      
      json = dumps({"body": body, 
                    "menu": menu, 
                    "title": 'Discover'})
    
      resp = Response(json, mimetype='application/json')
      return resp
    else:
      posts = []
      for feed in feeds:
        posts.append(render(feed, "feed", owner, 'discover')) 
      if len(feeds) == 0:
        posts.append(render_template('more.html', more_url=None))
      else:
        posts.append(render_template('more.html', 
                                     more_url='/%s/page%d' \
                                     % (request.path.split('/')[1], page+1)))
      
      return ''.join(posts)
  else:
    if not user_id:
  #    return render_homepage(session_id, 'Get work done. Faster. | Jupo', 
  #                           view='intro')
      return render_template('landing_page.html')
    else:
      return render_homepage(session_id, 'Discover', 
                             view='discover',
                             feeds=feeds)


@app.route('/invite', methods=['OPTIONS', 'POST'])
def invite():
  session_id = session.get("session_id")
  group_id = request.form.get('group_id', request.args.get('group_id'))
  
  if request.method == 'OPTIONS':
    user_id = api.get_user_id(session_id)
    owner = api.get_user_info(user_id)
    
    email_addrs = [i.email for i in owner.google_contacts]
    for user in owner.contacts:
      if user.email not in email_addrs:
        email_addrs.append(user.email)
        
    
    if group_id:
      group = api.get_group_info(session_id, group_id)
      title = 'Invite Friends to %s group' % group.name
    else:
      group = {}
      title = None
      
    return dumps({'title': title,
                  'body': render_template('invite.html', 
                                          title=title,
                                          email_addrs=email_addrs,
                                          group=group)})
  else:
    email = request.form.get('email', request.args.get('email'))
    if email:
      api.invite(session_id, email, group_id)
      return ' ✔ Done '
    else:
      addrs = request.form.get('to')
      msg = request.form.get('msg')
      if addrs:
        addrs = addrs.split(',')
        for addr in addrs:
          if addr.isdigit():
            email = api.get_user_info(addr).email
          else:
            email = addr
          api.invite(session_id, email, group_id=group_id, msg=msg)
        
        if group_id:
          return redirect('/group/%s?message=Invitation sent!' % group_id)
        else:
          return redirect('/news_feed?message=Invitation sent!')
      else:
        abort(400)



@app.route('/welcome', methods=['GET', 'OPTIONS'])
def welcome():
  if request.method == 'GET':
    session_id = session.get("session_id")
    return render_homepage(session_id, 'Getting Started', view='welcome')
  else:
    body = render_template('welcome.html', view='welcome')
    return dumps({'body': body, 
                  'title': 'Welcome to Jupo'})
    
    
@app.route('/notify_me', methods=['POST'])
def notify_me():
  email = request.form.get('email')
  if not email:
    abort(400, 'Missing email')
  state = api.notify_me(email)
  return 'Thank you!'


@app.route('/jobs')
def jobs():
  return redirect('http://bit.ly/17J9aYk')

  
@app.route("/<any(sign_in, sign_up, sign_out, forgot_password, reset_password):action>", methods=["GET", "OPTIONS", "POST"])
def authentication(action=None):
  hostname = request.headers.get('Host')
  
  db_name = hostname.replace('.', '_')
  
  primary_domain = '.'.join(settings.PRIMARY_DOMAIN.rsplit('.', 2)[-2:])
  if hostname != settings.PRIMARY_DOMAIN:
    network_info = api.get_network_info(db_name)
  else:
    network_info = {'name': 'Jupo'}
  
  if request.path.endswith('sign_in'):
    
    
    if request.method == 'OPTIONS':
      data = dumps({'title': 'Sign in to Jupo',
                    'body': render_template('sign_in.html', 
                                            domain=hostname, 
                                            PRIMARY_DOMAIN=settings.PRIMARY_DOMAIN)})
      resp = Response(data, mimetype='application/json')
      return resp
    
    elif request.method == "GET":
      email = request.args.get('email')
      msg = request.args.get('msg')
      if msg and email:
        resp = Response(render_template('sign_in.html', 
                                        msg=msg, email=email,
                                        domain=hostname, 
                                        PRIMARY_DOMAIN=settings.PRIMARY_DOMAIN,
                                        network_info=network_info))
      else:
        resp = Response(render_template('sign_in.html', 
                                        domain=hostname, 
                                        PRIMARY_DOMAIN=settings.PRIMARY_DOMAIN,
                                        network_info=network_info))
      return resp
      
    
    email = request.form.get("email")
    password = request.form.get("password")
    back_to = request.form.get('back_to', request.args.get('back_to'))
    user_agent = request.environ.get('HTTP_USER_AGENT')
    app.logger.debug(user_agent)
    remote_addr = request.environ.get('REMOTE_ADDR')
    session_id = api.sign_in(email, password, 
                             user_agent=user_agent, remote_addr=remote_addr)
    app.logger.debug(session_id)
    if session_id:
    
      # Sign in for all networks
      if db_name:
        db_names = api.get_db_names(email)
        if db_name not in db_names:
          api.add_db_name(email, db_name)
        
        for db in db_names:
          if db != db_name:
            api.update_session_id(email, session_id, db)

      
      session.permanent = True
      session['session_id'] = session_id
      if back_to:
        resp = redirect(back_to)
        resp.set_cookie('channel_id', api.get_channel_id(session_id)) 
      else:
        resp = redirect('/news_feed')  
        resp.set_cookie('channel_id', api.get_channel_id(session_id))
      return resp
    else:
      if not email:
        message = "The email field must not be empty"
      elif not password:
        message = "The password field must not be empty"
      else:
        if session_id is False:
          message = "Incorrect password. <a href='/forgot_password'>Reset password</a>"
        else:
          message = """No account found for this email.
          Retry, or <a href='/sign_up?email=%s'>Sign up for Jupo</a>""" % email
      resp = Response(render_template('sign_in.html', 
                                      domain=hostname,
                                      email=email, 
                                      password=password, 
                                      message=message,
                                      PRIMARY_DOMAIN=settings.PRIMARY_DOMAIN,
                                      network_info=network_info))
      return resp
        

  elif request.path.endswith('sign_up'):
    if request.method == 'GET':
      welcome = request.args.get('welcome')
      email = request.args.get('email')
      resp = Response(render_template('sign_up.html', 
                                      welcome=welcome,
                                      domain=hostname, 
                                      email=email,
                                      PRIMARY_DOMAIN=settings.PRIMARY_DOMAIN,
                                      network_info=network_info))
      return resp
        
    email = request.form.get('email').strip()
    name = request.form.get('name')
    password = request.form.get('password', '')
    
    alerts = {}
    if email and api.is_exists(email):
      alerts['email'] = '"%s" is already in use.' % email
    if len(password) < 6:
      alerts['password'] = 'Your password must be at least 6 characters long.'
    
    
    if alerts.keys():
      resp = Response(render_template('sign_up.html', 
                                      alerts=alerts,
                                      email=email,
                                      password=password,
                                      name=name,
                                      domain=hostname, 
                                      PRIMARY_DOMAIN=settings.PRIMARY_DOMAIN,
                                      network_info=network_info))
      return resp
    else:
      session_id = api.sign_up(email, password, name)
      if session_id:
        
        # Sign in for all networks
        if db_name:
          db_names = api.get_db_names(email)
          if db_name not in db_names:
            api.add_db_name(email, db_name)
          
          for db in db_names:
            if db != db_name:
              api.update_session_id(email, session_id, db)
              
        session['session_id'] = session_id
        
        user_id = api.get_user_id(session_id)
        if api.is_admin(user_id):
          return redirect('/groups')
        else:
          return redirect('/everyone?getting_started=1')  
      else:
        return redirect('/')
      
  elif request.path.endswith('sign_out'):
    session_id = session.get('session_id')
    if session_id:
      user_id = api.get_user_id(session_id)
      email = api.get_user_info(user_id).email
      
      app.logger.debug('sign out: %s' % session_id)
      api.set_status(session_id, 'offline')
      api.sign_out(session_id)
      session.pop('session_id')
      
      
      # Sign out all networks
      if db_name:
        db_names = api.get_db_names(email)
        if db_name not in db_names:
          api.add_db_name(email, db_name)
        
        for db in db_names:
          if db != db_name:
            api.sign_out(session_id, db_name=db)
      
    return redirect('/')
  
  elif request.path.endswith('forgot_password'):
    if request.method == 'GET':
      return render_template('forgot_password.html')  
    if request.method == 'OPTIONS':
      data = dumps({'title': 'Jupo - Forgot your password?',
                    'body': render_template('forgot_password.html')})
      return Response(data, mimetype='application/json')
    else:
      email = request.form.get('email')
      if not email:
        message = 'The email field must not be empty'
        ok = False
      else:
        r = api.forgot_password(email)
        if r is True:
          message = "We've sent you an email with instructions on how to reset your password. Please check your email."
          ok = True
        else:
          message = 'No one with that email address was found'
          ok = False
      return render_template('forgot_password.html', 
                             ok=ok,
                             message=message)
    
  elif request.path.endswith('reset_password'):
    if request.method == 'GET':
      code = request.args.get('code')
      return render_template('reset_password.html', code=code)
        
    else:
      code = request.form.get('code')
      email = api.FORGOT_PASSWORD.get(code)
      if not email:
        return render_template('reset_password.html', code=code,
                               message='Please provide a valid reset code')
        
      new_password = request.form.get('password')
      if not new_password:
        return render_template('reset_password.html', code=code, 
                               message='Please enter a new password for this account')
      elif len(new_password) < 6:
        return render_template('reset_password.html', code=code, 
                               message='Your password must be at least 6 characters long.')
        
      confirm_password = request.form.get('confirm')
      if new_password != confirm_password:
        return render_template('reset_password.html', code=code,
                               message='The two passwords you entered do not match')
        
      user_id = api.get_user_id_from_email_address(email)
      api.reset_password(user_id, new_password)
      api.FORGOT_PASSWORD.delete(code)
      
      return redirect('/sign_in?email=%s&msg=Your password has been reset' % email)
      
  


@app.route('/oauth/google')
def google_login():
  domain = request.args.get('domain', settings.PRIMARY_DOMAIN)
  
  return redirect('https://accounts.google.com/o/oauth2/auth?response_type=code&scope=https://www.googleapis.com/auth/userinfo.email+https://www.googleapis.com/auth/userinfo.profile+https://www.google.com/m8/feeds/&redirect_uri=%s&approval_prompt=auto&state=%s&client_id=%s&hl=en&from_login=1&as=-773fbbe34097e4fd&pli=1&authuser=0' \
                  % (settings.GOOGLE_REDIRECT_URI, domain, settings.GOOGLE_CLIENT_ID))

@app.route('/oauth/google/authorized')
def google_authorized():
  code = request.args.get('code')
  domain = request.args.get('state', settings.PRIMARY_DOMAIN)
  
  # get access_token
  url = 'https://accounts.google.com/o/oauth2/token'
  resp = requests.post(url, data={'code': code,
                                  'client_id': settings.GOOGLE_CLIENT_ID,
                                  'client_secret': settings.GOOGLE_CLIENT_SECRET,
                                  'redirect_uri': settings.GOOGLE_REDIRECT_URI,
                                  'grant_type': 'authorization_code'})
  data = loads(resp.text)
  
#  app.logger.debug(data)
  
  # fetch user info
  url = 'https://www.googleapis.com/oauth2/v1/userinfo'
  resp = requests.get(url, headers={'Authorization': '%s %s' \
                                    % (data.get('token_type'),
                                       data.get('access_token'))})
  user = loads(resp.text)
  
  
  url = 'https://www.google.com/m8/feeds/contacts/default/full/?max-results=5000'
  resp = requests.get(url, headers={'Authorization': '%s %s' \
                                    % (data.get('token_type'),
                                       data.get('access_token'))})
  contacts = api.re.findall("address='(.*?)'", resp.text)
  if contacts:
    contacts = list(set(contacts))
  
  db_name = domain.lower().strip().replace('.', '_')
  
  user_info = api.get_user_info(email=user.get('email'), db_name=db_name)
  session_id = api.sign_in_with_google(email=user.get('email'), 
                                       name=user.get('name'), 
                                       gender=user.get('gender'), 
                                       avatar=user.get('picture'), 
                                       link=user.get('link'), 
                                       locale=user.get('locale'), 
                                       verified=user.get('verified_email'),
                                       google_contacts=contacts,
                                       db_name=db_name)
  
  if db_name:
    email = user.get('email')
    if email:
      db_names = api.get_db_names(email)
      if db_name not in db_names:
        api.add_db_name(email, db_name)
      
      for db in db_names:
        if db != db_name:
          api.update_session_id(email, session_id, db)
  
  if domain == settings.PRIMARY_DOMAIN:
    session['session_id'] = session_id
    if user_info.id:
      return redirect('/')
    else: # new user
      return redirect('/everyone?getting_started=1')
  else:
    url = 'http://%s/?session_id=%s' % (domain, session_id)
    resp = redirect(url)
    return resp
  
  
  
  
  
    
if settings.FACEBOOK_APP_ID and settings.FACEBOOK_APP_SECRET:
  facebook = oauth.remote_app('facebook',
      base_url='https://graph.facebook.com/',
      request_token_url=None,
      access_token_url='/oauth/access_token',
      authorize_url='https://www.facebook.com/dialog/oauth',
      consumer_key=settings.FACEBOOK_APP_ID,
      consumer_secret=settings.FACEBOOK_APP_SECRET,
      request_token_params={'scope': 'email'}
  )
  
  @app.route('/oauth/facebook')
  def facebook_login():
    if not facebook:
      abort(501)
  #  return facebook.authorize(callback='http://play.jupo.com/oauth/facebook/authorized')
    callback_url = url_for('facebook_authorized',
                           domain=request.args.get('domain', settings.PRIMARY_DOMAIN),
                           _external=True)
    app.logger.debug(callback_url)
    return facebook.authorize(callback=callback_url)
  
  
  
  @app.route('/oauth/facebook/authorized')
  @facebook.authorized_handler
  def facebook_authorized(resp):
    domain = request.args.get('domain', settings.PRIMARY_DOMAIN)
    
    if resp is None:
      return 'Access denied: reason=%s error=%s' % (request.args['error_reason'],
                                                    request.args['error_description'])
    session['facebook_access_token'] = (resp['access_token'], '')
    
    if request.args.get('fb_source') == 'notification':
      return redirect('/')
    
    retry_count = 0
    while retry_count < 3:
      try:
        me = facebook.get('/me')
        break
      except:
        retry_count += 1
        sleep(1)
        
    retry_count = 0
    while retry_count < 3:    
      try:
        friends = facebook.get('/me/friends?limit=5000')
        break
      except:
        retry_count += 1
        sleep(1)
    
    facebook_id = me.data['id']
    friend_ids = [i['id'] for i in friends.data['data'] if isinstance(i, dict)]
  
    db_name = domain.lower().strip().replace('.', '_')
    
    user_info = api.get_user_info(email=me.data.get('email'), db_name=db_name)
  
    session_id = api.sign_in_with_facebook(email=me.data.get('email'), 
                                           name=me.data.get('name'), 
                                           gender=me.data.get('gender'), 
                                           avatar='https://graph.facebook.com/%s/picture' % facebook_id, 
                                           link=me.data.get('link'), 
                                           locale=me.data.get('locale'), 
                                           timezone=me.data.get('timezone'), 
                                           verified=me.data.get('verified'), 
                                           facebook_id=facebook_id,
                                           facebook_friend_ids=friend_ids,
                                           db_name=db_name)
    
    if db_name:
      email = me.data.get('email')
      if email:
        db_names = api.get_db_names(email)
        if db_name not in db_names:
          api.add_db_name(email, db_name)
        
        for db in db_names:
          if db != db_name:
            api.update_session_id(email, session_id, db)
          
    if domain == settings.PRIMARY_DOMAIN:
      session['session_id'] = session_id
      if user_info.id:
        return redirect('/')
      else: # new user
        return redirect('/everyone?getting_started=1')
    else:
      url = 'http://%s/?session_id=%s' % (domain, session_id)
      resp = redirect(url)
      return resp
  
  
  @facebook.tokengetter
  def get_facebook_token():
    return session.get('facebook_access_token') 
  
  

@app.route('/reminders', methods=['GET', 'OPTIONS', 'POST'])
@app.route('/reminder/new', methods=["POST"])
@app.route('/reminder/<int:reminder_id>/check', methods=["POST"])
@app.route('/reminder/<int:reminder_id>/uncheck', methods=["POST"])
@login_required
@line_profile
def reminders(reminder_id=None):
  session_id = session.get("session_id")
  message = request.form.get('message')
  if request.path.endswith('/new'):
    id = api.new_reminder(session_id, message)
    return str(id)
  elif request.path.endswith('/check'):
    api.check(session_id, reminder_id)
    return 'Done'
  elif request.path.endswith('/uncheck'):
    api.uncheck(session_id, reminder_id)
    return 'Done'
  else:
    reminders_list = api.get_reminders(session_id)
    if request.method == 'GET':
      return render_homepage(session_id, 'Reminders',
                             view='reminders',
                             reminders=reminders_list)
    else:
      body = render_template('reminders.html', 
                             view='reminders',
                             reminders=reminders_list)
      
      json = dumps({"body": body, 
                    "title": 'Reminders'})
      return Response(json, mimetype='application/json') 
  

  
@app.route("/notes", methods=['GET', 'OPTIONS'])
@app.route("/notes/page<int:page>", methods=['OPTIONS'])
@login_required
@line_profile
def notes(page=1):
  view = 'notes'
  session_id = session.get("session_id")
  user_id = api.get_user_id(session_id)
  owner = api.get_user_info(user_id)
  
  title = "Notes"
  notes = api.get_notes(session_id, page=page)
  
  if page == 1:
    reference_notes = api.get_reference_notes(session_id, 10)
  else:
    reference_notes = []
  
  app.logger.debug(notes)
      
  
  if request.method == "OPTIONS":
    if page > 1:
      stream = ''
      posts = []
      for note in notes:
        posts.append(render(note, "note", owner, view, request=request))  
      if len(notes) == 0:
        posts.append(render_template('more.html', more_url=None))
      else:
        posts.append(render_template('more.html', 
                                     more_url='/notes/page%d' % (page+1)))
      return ''.join(posts)
    else:
      menu = render_template('menu.html', 
                             view=view)
      body = render_template('notes.html', 
                             view=view,  
                             title=title, 
                             owner=owner,
                             request=request,
                             reference_notes=reference_notes,
                             notes=notes)
  
      
      json = dumps({"body": body, 
                    "menu": menu, 
                    "title": title})
      return Response(json, mimetype='application/json') 
  else:
    return render_homepage(session_id, title,
                           view=view,
                           reference_notes=reference_notes,
                           notes=notes)
    

@app.route("/note/new", methods=["GET", "OPTIONS", "POST"])
@app.route("/note/<int:note_id>", methods=["GET", "OPTIONS"])
@app.route("/note/<int:note_id>/edit", methods=["OPTIONS"])
@app.route("/note/<int:note_id>/v<int:version>", methods=["OPTIONS", "POST"])
@app.route("/note/<int:note_id>/<action>", methods=["GET", "OPTIONS", "POST"])
@line_profile
def note(note_id=None, action=None, version=None):  
  session_id = session.get("session_id")
  owner = api.get_owner_info(session_id)
  content = info = None
  if request.path == '/note/new':
    if request.method == 'GET':
      note = {}
      title = 'New Note'
      mode = 'edit'
      view = 'notes'
      return render_homepage(session_id, title,
                             view=view,
                             note=note, mode=mode)
    elif request.method == 'OPTIONS':
      title = 'New Note'
      mode = 'edit'
      note = {}
    else:
      title = request.form.get('title', 'Untitled Note')
      content = request.form.get('content')
      note_id = request.form.get('note_id')
          
      viewers = request.form.get('viewers')
      if viewers:
        viewers = viewers.split(',')
      else:
        viewers = []
      
      attachments = request.form.get('attachments')
      if attachments:
        attachments = attachments.rstrip(',').split(',')
      else:
        attachments = []

      note_id = api.new_note(session_id, title, content, attachments, viewers)
      
      return dumps({'redirect': '/note/%s' % note_id})


  elif action and action == 'last_changes':
    note = api.compare_with_previous_version(session_id, note_id, revision=0)
    mode = 'view'
    action = 'compare'
    title = 'Notes - Track changes'
    

  elif version is not None:
    app.logger.debug(version)
    note = api.get_note(session_id, note_id, version)
    mode = 'view'
    title = '%s v%s | Jupo Notes' % (note.title, version)
    
  elif request.path.endswith('/edit'):
    note = api.get_note(session_id, note_id)
    title = 'Notes - EditMode - %s' % note.title
    mode = 'edit'
    
  elif action == 'update':    
    title = request.form.get('title', 'Untitled Note')
    content = request.form.get('content')
    viewers = request.form.get('viewers')
    if viewers:
      viewers = viewers.split(',')
    else:
      viewers = []      
    
    attachments = request.form.get('attachments')
    app.logger.debug(attachments)
    if attachments:
      attachments = attachments.rstrip(',').split(',')
    else:
      attachments = []
    
    if note_id:
      api.update_note(session_id, note_id, title, content, attachments, viewers)
    else:
      note_id = api.new_note(session_id, title, content, attachments, viewers)
      
    return dumps({'redirect': '/note/%s' % note_id})
    
  elif action == 'remove':
    session_id = session.get("session_id")
    id = api.remove_note(session_id, note_id)
    return id
  
  elif action == 'mark_official':
    api.mark_official(session_id, note_id)
    return 'Done'
  
  elif action == 'mark_unofficial':
    api.mark_unofficial(session_id, note_id)
    return 'Done'
  
  elif action == 'mark_as_read':
    api.mark_as_read(session_id, note_id)
    return ':)'
  
#  elif action and action.startswith('restore_from_'):
#    revision = action.lstrip('restore_from_')
#    if revision.isdigit():
#      api.restore_note(session_id, note_id, int(revision))
#      note = api.get_note(session_id, note_id)
#      title = 'Notes - %s' % info.title
#      mode = 'view'
#    else:
#      pass  #TODO: return an error page with code = 405 
    
  elif action == 'comment':
    message = request.form.get('message')
    comment = api.new_comment(session_id, message, note_id)
    return render_template('comment.html', 
                           comment=comment,
                           owner=owner,
                           prefix='note')
  
  else:
    note = api.get_note(session_id, note_id)
    
    if not session_id and note is False:
      return redirect('/?back_to=%s' % request.path)
    
    mode = 'view'
    
#   recents = api.get_notes(session_id, limit=5) 
  if note is False or (note and not note.id):
    abort(404)
  
  view = 'notes'
  if version is None and info:
    version = len(note.to_dict()['version'])

  group_id = request.args.get('group_id')
  if group_id:
    group = api.get_group_info(session_id, group_id)
  else:
    group = None  
  
  if request.method in ["POST", "OPTIONS"]:
    body = render_template('notes.html', 
                           view='notes',
                           mode=mode,
                           action=action,
                           version=version,
                           note=note,
                           group=group,
                           owner=owner,
                           content=content)
    info = {'body': body}
    if note:
      info['title'] = note.title 
    else:
      info['title'] = 'Untitle Note'
    return Response(dumps(info), mimetype='application/json')
  else:
    full = True if 'full' in request.query_string else False
    if not owner.id or full is True:
      title = note.title
      description = note.content
      return render_template('post.html',
                             owner=owner,
                             mode='view',
                             full=True,
                             title=title, description=description, 
                             note=note)
    else:
      return render_homepage(session_id, note.title,
                             version=version,
                             group=group, note=note, view='notes', mode='view')

@app.route('/u<key>')
@app.route('/u/<int:note_id>')
def share_to_anyone_with_the_link(note_id=None, key=None):
  session_id = session.get("session_id")
  if key:
    doc = api.get_doc_by_key(key)            
    return render_homepage(session_id, 'Note',
                           view='discover', mode='view', doc=doc)
    
  else:
    key = api.get_key(session_id, note_id)
    if not key:
      abort(404)
    return redirect('/u' + key)
  


#===============================================================================
# Files
#===============================================================================

@app.route("/public/<path:filename>")
def public_files(filename):
  filedata = cache.get('file:%s' % os.path.basename(filename)) \
             if not settings.DEBUG else None
  
  if not filedata:
    path = os.path.join(os.path.dirname(__file__), 'public', filename)
    if not os.path.exists(path):
      abort(404, 'File not found')
    filedata = open(path).read()  
      
  response = make_response(filedata)
  response.headers['Content-Length'] = len(filedata)
  response.headers['Content-Type'] = guess_type(filename)[0]
  response.headers['Cache-Control'] = 'public'
  response.headers['Expires'] = '31 December 2037 23:59:59 GMT'
  return response


@app.route("/favicon.ico")
def favicon():
  path = 'public/favicon.ico'
  filedata = open(path).read()
  response = make_response(filedata)
  response.headers['Content-Length'] = len(filedata)
  response.headers['Content-Type'] = 'image/x-icon'
  return response


@app.route('/update_profile_picture', methods=['POST'])
@app.route('/user/<int:user_id>', methods=['GET', 'OPTIONS'])
@app.route('/user/<int:user_id>/page<int:page>', methods=['GET', 'OPTIONS'])
@app.route('/user/<int:user_id>/update', methods=['POST'])
@app.route('/user/<int:user_id>/complete_profile', methods=['POST'])
@app.route('/user/<int:user_id>/follow', methods=['POST'])
@app.route('/user/<int:user_id>/unfollow', methods=['POST'])
@app.route('/user/<int:user_id>/<view>', methods=['GET', 'OPTIONS'])
@login_required
@line_profile
def user(user_id=None, page=1, view=None):
  session_id = session.get("session_id") 
    
  if request.path == '/update_profile_picture':
    fid = request.args.get('fid')
    api.update_user_info(session_id, {'avatar': long(fid)})
    return 'OK'
  
  owner = api.get_owner_info(session_id)
  user = api.get_user_info(user_id)
  if not user.id:
    abort(404)
      
  if view in ['edit', 'update_profile']:
    resp = {'title': 'Update Profile',
            'body': render_template('user.html',
                                    mode='edit', 
                                    view='update_profile',
                                    owner=owner)}
    return Response(dumps(resp), mimetype='application/json')

  elif view == 'change_password':
    resp = {'title': 'Change Password',
            'body': render_template('user.html',
                                    mode='change_password', 
                                    owner=user)}
    return Response(dumps(resp), mimetype='application/json')
    
  elif request.path.endswith('/complete_profile'):
    name = request.form.get('name')
    gender = request.form.get('gender')
    
    password = request.form.get('password')
    avatar = request.files.get('file')
    
    fid = api.new_attachment(session_id, avatar.filename, avatar.stream.read())
    new_session_id = api.complete_profile(session_id, 
                                          name, password, gender, fid)
    
    resp = redirect('/everyone?getting_started=1')  
    if new_session_id:
      session['session_id'] = new_session_id
    return resp
    
  elif request.path.endswith('/update'):
    old_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_new_password = request.form.get('confirm_new_password')
    
    if not new_password:
      return redirect('/?message=New password must not be empty')
      
    
    if old_password:
      if new_password != confirm_new_password:
        return redirect('/?message=New password does not match')
      else:
        ok = api.change_password(session_id, old_password, new_password)
        
        api.set_status(session_id, 'offline')
        api.sign_out(session_id)
        session.pop('session_id')
        
        return redirect('/?message=Password updated successfully.')
    
    if not old_password and new_password and new_password == confirm_new_password:
      if owner.has_password():
        return redirect('/?message=Please enter your current password.')
      else:
        user_id = api.get_user_id(session_id)
        api.reset_password(user_id, new_password)
        return redirect('/?message=New password updated successfully.')
    
    
    name = request.form.get('name')
    gender = request.form.get('gender')
    
      
    intro = request.form.get('intro')
    location = request.form.get('location')
    
    if location:
      info = {'name': name,
              'gender': gender,
              'location': location,
              'introduction': intro}
    else:
      info = {'name': name,
              'gender': gender,
              'introduction': intro}
      
    
    disabled_notifications = []
    if not request.form.get('comments'):
      disabled_notifications.append('comments')
    if not request.form.get('share_posts'):
      disabled_notifications.append('share_posts')
    if not request.form.get('mentions'):
      disabled_notifications.append('mentions')  
      
    info['disabled_notifications'] = disabled_notifications
    
    birthday_day = request.form.get('birthday-day')
    birthday_month = request.form.get('birthday-month')
    birthday_year = request.form.get('birthday-year')
    if birthday_day.isdigit() and birthday_month.isdigit() and birthday_year.isdigit():
      info['birthday'] = '%s/%s/%s' % (birthday_day, birthday_month, birthday_year)
      
    
    phone = request.form.get('phone')
    if phone.replace('+', '').replace(' ', '').isdigit():
      info['phone'] = phone
    
    fid = request.form.get('fid')
    if fid:
      info['avatar'] = long(fid)
    api.update_user_info(session_id, info)
    return redirect('/news_feed')
        
  elif request.path.endswith('/follow'):
    api.add_to_contacts(session_id, user_id)
#    api.follow(session_id, user_id)
    return 'Done'
  
  elif request.path.endswith('/unfollow'):
    api.remove_from_contacts(session_id, user_id)
#    api.unfollow(session_id, user_id)
    return 'Done'
  
  elif view == 'groups':
    return dumps({'body': render_template('groups.html',
                                          user=user,
                                          owner=owner,
                                          groups=user.groups)})
  elif view == 'followers':
    users = [api.get_user_info(user_id) for user_id in user.followers]
    return dumps({'body': render_template('users.html', 
                                          title='Followers',
                                          users=users)})
  
  elif view == 'following':
    users = [api.get_user_info(user_id) for user_id in user.following_users]
    return dumps({'body': render_template('users.html', 
                                          title='Following',
                                          users=users)})
    
  elif view == 'starred':
    posts = api.get_starred_posts(api.get_session_id(user_id))
    body = render_template('user.html', 
                           title='Starred', 
                           category = 'starred',
                           view='user',
                           user=user,
                           owner=owner,
                           feeds=posts)
    json = dumps({'body': body, 'title': 'Intelliview'})
    return Response(json, mimetype='application/json')
    

  else:
    
    view = 'user'
    title = user.name
    
    
    if not session_id or owner.id == user.id:
      feeds = api.get_public_posts(user_id=user.id, page=page)
    else:
      feeds = api.get_user_posts(session_id, user_id, page=page)

    user.recent_files = api.get_user_files(session_id, user_id=user.id, limit=3)
    user.recent_notes = api.get_user_notes(session_id, user_id=user.id, limit=3)
    
    coworkers = [user]
    if request.method == "OPTIONS":   
        
      if page == 1:
        body = render_template('user.html', 
                               view=view, 
                               user=user,
                               owner=owner,
                               title=title, 
                               coworkers=coworkers,
                               feeds=feeds)
        
        json = dumps({"body": body, 
                      "title": title})
        return Response(json, mimetype='application/json')
      else:
        posts = [render(feeds, 'feed', owner, 'user')]
          
        if len(feeds) == 0:
          posts.append(render_template('more.html', more_url=None))
        else:
          posts.append(render_template('more.html', 
                                       more_url='/user/%s/page%d' \
                                       % (user_id, page+1)))
        return ''.join(posts)
      
      
      
    else:
      return render_homepage(session_id, title,
                             coworkers=coworkers,
                             user=user,
                             feeds=feeds, view=view)
  


@app.route("/contacts", methods=["GET", "OPTIONS"])
@login_required
def contacts():
  session_id = session.get("session_id")
  user_id = api.get_user_id(session_id)
  owner = api.get_user_info(user_id)
  body = render_template('contacts.html',
                         owner=owner)
  return Response(dumps({'body': body,
                         'title': 'Contacts'}), 
                  mimetype='application/json')  
  


@app.route("/networks", methods=['OPTIONS'])
@login_required
def networks():
  session_id = session.get("session_id")
  user_id = api.get_user_id(session_id)
  if not user_id:
    abort(400)
    
  owner = api.get_user_info(user_id)
  resp = {'body': render_template('networks.html', owner=owner),
          'title': 'Networks'}
  return Response(dumps(resp), mimetype='application/json')


@app.route("/network/new", methods=['GET', 'POST'])
def network():
  if request.path.endswith('/new'):
    
    domain = subdomain = organization_name = msg = None
    
    
    if request.method == 'POST':
      domain = request.form.get('domain')
      organization_name = request.form.get('name')
      
        
      if domain:
        if  '.' not in domain:
          msg = 'The domain you entered was invalid.'
        elif not api.domain_is_ok(domain):
          msg = '''\
          Please make sure <strong>%s</strong> is mapped to <strong>play.jupo.com</strong>.<br>
          If you already do it, please try again after few minutes. <br>
          Normally it takes some time once you update your DNS records<br>
          until the changes take effect around the world.''' % (domain)
        
      subdomain = request.form.get('subdomain')
      
      if subdomain and len(subdomain) > 50:
        msg = 'Subdomain is too long.'
        
      if subdomain and not api.domain_is_ok(subdomain + '.jupo.com'):
        msg = 'Subdomain already exists.'
        
      if not subdomain and not domain:
        msg = 'Please enter a domain or choose a subdomain.'
        
      if not organization_name:
        msg = 'Please enter your organization name.'
        
      
      if not msg:
          
        # TODO: check subdomain is valid (a-Z0-9)
        if subdomain:
          db_name = subdomain.lower().strip() + '_jupo_com'
          if api.is_exists(db_name=db_name):
            msg = 'Subdomain already exists.'
        elif domain:
          db_name = domain.lower().strip().replace('.', '_')
          if api.is_exists(db_name=db_name):
            msg = 'Domain already exists.'
        
        if db_name and not msg:
          api.new_network(db_name, organization_name)
          if subdomain:
            return redirect('http://%s.jupo.com/sign_up?welcome=1' % subdomain)
          else:
            return redirect('http://%s/sign_up?welcome=1' % domain)
      
        
    return render_template('new_network.html', 
                           ip=api.PRIMARY_IP,
                           organization_name=organization_name,
                           domain=domain,
                           subdomain=subdomain,
                           message=msg)



@app.route("/everyone", methods=["GET", "OPTIONS"])
@app.route("/everyone/page<int:page>", methods=["GET", "OPTIONS"])
@app.route("/people", methods=["GET", "OPTIONS"])
@app.route("/groups", methods=["GET", "OPTIONS"])
@app.route("/group/new", methods=["GET", "OPTIONS", "POST"])
@app.route("/group/<int:group_id>/update", methods=["POST"])
@app.route("/group/<int:group_id>/follow", methods=["POST"])
@app.route("/group/<int:group_id>/unfollow", methods=["POST"])
@app.route("/group/<int:group_id>/highlight", methods=["POST"])
@app.route("/group/<int:group_id>/unhighlight", methods=["POST"])
@app.route("/group/<int:group_id>/add_member", methods=["POST"])
@app.route("/group/<int:group_id>/remove_member", methods=["POST"])
@app.route("/group/<group_id>/make_admin", methods=["POST"])
@app.route("/group/<group_id>/remove_as_admin", methods=["POST"])
@app.route("/group/<int:group_id>", methods=["GET", "OPTIONS"])
@app.route("/group/<int:group_id>/page<int:page>", methods=["OPTIONS"])
@app.route("/group/<int:group_id>/<view>", methods=["GET", "OPTIONS"])
@login_required
@line_profile
def group(group_id=None, view='group', page=1):
  hostname = request.headers.get('Host')
  
  session_id = session.get("session_id")    
  user_id = api.get_user_id(session_id)
  if not user_id:
    return redirect('/?continue=%s' % request.path)
  
  owner = api.get_user_info(user_id)
  
  hashtag = request.args.get('hashtag')

    
  if request.path.startswith('/everyone'):
    group_id = 'public'

  if request.path == '/people':
    group_id = 'public'
    view = 'members'
    
  
  if request.path.endswith('/new'):
    if request.method == 'GET':
      name = request.args.get('name')
      description = request.args.get('description')
      return render_homepage(session_id, 'Groups',
                             name=name,
                             description=description,
                             view='new-group')
      
    name = request.form.get('name')
    if name:
      privacy = request.form.get('privacy', 'closed')
      about = request.form.get('about')
      group_id = api.new_group(session_id, 
                               name, privacy,
                               about=about)

      return str(group_id)
    
    else:     
      name = request.args.get('name')
      description = request.args.get('description')
      body = render_template('new.html', 
                             name=name,
                             description=description,
                             owner=owner,
                             view='new-group')
      return Response(dumps({'title': 'New Group',
                             'body': body}), mimetype='application/json')
    
  if request.path.endswith('/follow'):
    is_ok = api.join_group(session_id, group_id)
    return 'Done'

  elif request.path.endswith('/unfollow'):
    api.leave_group(session_id, group_id)
    return 'Done'

  elif request.path.endswith('/highlight'):
    note_id = request.args.get('note_id')
    api.highlight(session_id, group_id, note_id)
    return 'Done'

  elif request.path.endswith('/unhighlight'):
    note_id = request.args.get('note_id')
    api.unhighlight(session_id, group_id, note_id)
    return 'Done'
    
  elif request.path.endswith('/add_member'):
    user_id = request.args.get('user_id')
    api.add_member(session_id, group_id, user_id)
    return 'Done' 
  
  elif request.path.endswith('/remove_member'):
    user_id = request.args.get('user_id')
    api.remove_member(session_id, group_id, user_id)
    return 'Done' 
  
  elif request.path.endswith('/make_admin'):
    user_id = request.args.get('user_id')
    api.make_admin(session_id, group_id, user_id)
    return 'Done' 
  
  elif request.path.endswith('/remove_as_admin'):
    user_id = request.args.get('user_id')
    api.remove_as_admin(session_id, group_id, user_id)
    return 'Done' 
  
  
      
  elif request.path.endswith('/update'):
    name = request.form.get('name')
    about = request.form.get('about')
    privacy = request.form.get('privacy', 'closed')
    post_permission = request.form.get('post_permission', 'members')
    
    trello_app_key = request.form.get('trello_app_key', None)
    trello_token = request.form.get('trello_token', None)
    trello_board_id = request.form.get('trello_board_id', None)
    
    
    info = {'name': name,
            'privacy': privacy,
            'post_permission': post_permission,
            'about': about}
    
    if trello_app_key and trello_token and trello_board_id:
      info['trello_app_key'] = trello_app_key
      info['trello_token'] = trello_token
      info['trello_board_id'] = trello_board_id 
    
    members = request.form.get('members')
    if members:
      members = [int(i) for i in members.split(',')]
    else:
      members = []
  
    if members:
      info['members'] = members
    
    admins = request.form.get('administrators')
    if admins:
      admins = [int(i) for i in admins.split(',')]
    else:
      admins = []
    if user_id not in admins:
      admins.append(user_id)
  
    if admins:    
      info['leaders'] = admins
    
    fid = request.form.get('fid')
    if fid:
      info['avatar'] = long(fid)
    api.update_group_info(session_id, group_id, info)
    return redirect('/group/%s' % group_id)
    
  if not group_id:
    groups = api.get_groups(session_id)
    
    
    featured_groups = default_groups = []
    
    _default_groups = [
      {'name': 'Sales & Marketing', 
       'description': 'Where the stories are made up and deals are closed'},
      {'name': 'IT',
       'description': 'We repeatedly fix what you repeatedly break'},
      {'name': 'Test & QA',
       'description': 'We make people feel bad about their work'},
      {'name': 'R&D',
       'description': 'Our favorite page is Google.com'},
      {'name': 'Design',
       'description': 'Design is now how it looks. Design is what the boss likes'},
      {'name': 'Customer Services',
       'description': 'Getting yelled at for things you can’t do anything about'}
    ]
    
    if api.is_admin(user_id):
      group_names = [group.name for group in groups]
      default_groups = []
      for group in _default_groups:
        if group['name'] not in group_names:
          default_groups.append(group)
    else:
      featured_groups = api.get_featured_groups(session_id)
      if not groups and not featured_groups:
        default_groups = _default_groups
    
    
    if request.method == 'GET':
      return render_homepage(session_id, 'Groups',
                             groups=groups,
                             featured_groups=featured_groups,
                             default_groups=default_groups,
                             view='groups')

    else:
      body = render_template('groups.html', 
                             view='groups',
                             owner=owner,
                             featured_groups=featured_groups,
                             default_groups=default_groups,
                             groups=groups)
      resp = Response(dumps({'body': body,
                             'title': 'Groups'}))
      return resp
    
  
  group = api.get_group_info(session_id, group_id)  
  if view == 'edit':
    resp = {'title': 'Group Settings',
            'body': render_template('group.html',
                                    hostname=hostname,
                                    mode='edit', 
                                    group=group)}
    return Response(dumps(resp), mimetype='application/json')
    
  
  elif view == 'docs':  
#    group.docs = api.get_docs_count(group_id)
#    group.files = api.get_files_count(group_id)
    
    owner = api.get_owner_info(session_id)
    docs = api.get_notes(session_id, group_id=group_id)
    if request.method == 'OPTIONS':
      body = render_template('group.html', 
                             group=group,
                             owner=owner,
                             mode='docs', 
                             docs=docs)
      resp = Response(dumps({'body': body}), mimetype='application/json')
      return resp
    else:
      return render_homepage(session_id, "%s's Notes" % group.name,
                             view='group',
                             mode='docs',
                             group=group,
                             docs=docs)
  
  elif view == 'files':
    abort(404)
    
  elif view == 'events':
    events = api.get_events(session_id, group_id, as_feeds=True)
    body = render_template('events.html', events=events, owner=owner)
    return dumps({'body': body, 'title': 'Events'})
  
  elif view == 'members':
#     app.logger.debug('aaaaaaAAAAAAAAAAAAAAA')
    
#     group.docs = api.get_docs_count(group_id)
#     group.files = api.get_files_count(group_id)
    
    owner = api.get_owner_info(session_id)
#     body = render_template('group.html', 
#                            view='members',
#                            group=group, owner=owner)
#     return dumps({'body': body})
  
    body = render_template('members.html', group=group, owner=owner)

    
    return Response(dumps({'body': body,
                           'title': "%s's Members" % group.name}), 
                    mimetype='application/json')  
  
  else:   
    
    if not group.id:
      abort(404)
    
    if group_id == 'public':
      feeds = api.get_public_posts(session_id, page=page)
    else:
      feeds = api.get_feeds(session_id, group_id, page=page)  
      api.add_to_recently_viewed_list(session_id, group_id)
  
    if not group.highlight_ids:
      group.recent_notes = api.get_notes(session_id, group_id=group_id, limit=3)
    group.recent_files = api.get_attachments(session_id, 
                                             group_id=group_id, limit=3)
    
    owner = api.get_owner_info(session_id)
    
    if request.method == 'OPTIONS':
      if page > 1:
        posts = [render(feeds, "feed", owner, view, group=group)]
          
        if len(feeds) == 0:
          posts.append(render_template('more.html', more_url=None))
        elif group_id == 'public':
          posts.append(render_template('more.html', 
                                       more_url='/everyone/page%d' % (page+1)))
        else:
          posts.append(render_template('more.html', 
                                       more_url='/group/%s/page%d' \
                                       % (group_id, page+1)))
        return ''.join(posts)
      else:
#        upcoming_events = api.get_upcoming_events(session_id, group_id)
      
        
        resp = {'title': group.name, 
                'body': render_template('group.html', 
                                        feeds=feeds, 
                                        group=group,
                                        owner=owner,
#                                        upcoming_events=upcoming_events,
                                        view=view)}
        
        json = dumps(resp)
        resp = Response(json, mimetype='application/json')
        
        return resp
    else:
      stats = {}
      groups = api.get_groups(session_id)
#      upcoming_events = api.get_upcoming_events(session_id, group_id)
      
      resp = render_homepage(session_id, 
                             group.name,
                             feeds=feeds, 
                             view=view, 
                             group=group,
#                             upcoming_events=upcoming_events,
                            )    
#      resp.set_cookie('last_g%s' % group_id, api.utctime())
      return resp


@app.route('/chat/user/<int:user_id>', methods=['GET', 'OPTIONS'])
@app.route('/chat/user/<int:user_id>/<action>', methods=['POST'])
@app.route('/chat/topic/<int:topic_id>', methods=['GET', 'OPTIONS'])
@app.route('/chat/topic/<int:topic_id>/<action>', methods=['OPTIONS', 'POST'])
@login_required
def chat(topic_id=None, user_id=None, action=None):
  session_id = session.get("session_id")
  timestamp = request.args.get('ts')
  
  if action == 'new_message':    
    msg = request.form.get('message')
    codeblock = request.form.get('codeblock')
    if '\n' in msg.strip() and codeblock:
      codeblock = True
    else:
      codeblock = False
    html = api.new_message(session_id, msg, 
                           user_id=user_id, 
                           topic_id=topic_id,
                           is_codeblock=codeblock)
    return html
  
  elif action == 'new_file':
    file = request.files.get('file')
    filename = file.filename
    attachment_id = api.new_attachment(session_id, 
                                       file.filename, 
                                       file.stream.read())
    
    html = api.new_message(session_id, attachment_id, 
                           user_id=user_id, topic_id=topic_id)
    return html
  
  elif action == 'mark_as_read':
    owner_id = api.get_user_id(session_id)
    if user_id:
      api.update_last_viewed(owner_id, user_id=user_id)
    else:
      api.update_last_viewed(owner_id, topic_id=topic_id)
      
    return 'OK'
  
  elif action == 'update':
    name = request.args.get('name')
    api.update_topic(session_id, topic_id, name)
    return 'OK'
  
  elif action == 'members':
    topic = api.get_topic_info(topic_id)
    owner = api.get_owner_info(session_id)
    body = render_template('topic_members.html', topic=topic, owner=owner)

    return Response(dumps({'body': body}), 
                    mimetype='application/json')  
    
  else:
    if request.method == 'GET':
      if user_id:
        return redirect('/messages/user/%s' % user_id)
      elif topic_id:
        return redirect('/messages/topic/%s' % topic_id)
      else:
        abort(400)
        
    owner_id = api.get_user_id(session_id)
    user = topic = seen_by = None
    if user_id:
      user = api.get_user_info(user_id)
      messages = api.get_chat_history(session_id, 
                                      user_id=user_id, 
                                      timestamp=timestamp)
      
      if not timestamp:
        last_viewed = api.get_last_viewed(user_id, owner_id) \
                    + int(api.get_utcoffset(owner_id))
                    
        last_viewed_friendly_format = api.friendly_format(last_viewed, short=True)
        if last_viewed_friendly_format.startswith('Today'):
          last_viewed_friendly_format = last_viewed_friendly_format.split(' at ')[-1]
        
        
        if messages and (messages[-1].sender.id == owner_id) and (messages[-1].timestamp < last_viewed):
          seen_by = 'Seen %s' % last_viewed_friendly_format
          
    else:
      last_viewed = last_viewed_friendly_format = 0
      topic = api.get_topic_info(topic_id)
      messages = api.get_chat_history(session_id, 
                                      topic_id=topic_id, 
                                      timestamp=timestamp)  
      
      if not timestamp:
        if messages:
          utcoffset = int(api.get_utcoffset(owner_id))
          last_viewed = {}
          seen_by = []
          for i in topic.member_ids:
            ts = api.get_last_viewed(i, topic_id=topic_id) + utcoffset
            last_viewed[i] = ts
            if messages[-1].timestamp < ts:
              seen_by.append(i)
        
        if seen_by:
          if len(seen_by) >= len(topic.member_ids):
            seen_by = 'Seen by everyone.'
          elif len(seen_by) == 1 and seen_by[0] == owner_id:
            seen_by = None
          else:
            seen_by = 'Seen by %s' % ', '.join([api.get_user_info(i).name \
                                                for i in seen_by \
                                                if i != owner_id])
            
    
    if timestamp:
      return render_template('messages.html', 
                             owner={'id': owner_id},
                             timestamp=timestamp,
                             messages=messages, user=user, topic=topic)
    else:
      return render_template('chatbox.html', 
                             owner={'id': owner_id},
                             seen_by=seen_by,
                             timestamp=timestamp,
                             messages=messages, user=user, topic=topic)
    
    

@app.route("/messages", methods=['GET', 'OPTIONS'])
@app.route("/messages/archived", methods=['GET', 'OPTIONS'])
@app.route("/messages/user/<int:user_id>", methods=['GET', 'OPTIONS'])
@app.route("/messages/topic/<int:topic_id>", methods=['GET', 'OPTIONS'])
@app.route("/messages/topic/<int:topic_id>/<action>", methods=['POST'])
@login_required
@line_profile
def messages(user_id=None, topic_id=None, action=None):
  session_id = session.get("session_id")
  
  if topic_id and request.method == 'POST':
    if action == 'archive':
      api.archive_topic(session_id, topic_id)
    elif action == 'unarchive':
      api.unarchive_topic(session_id, topic_id)
    elif action == 'leave':
      api.leave_topic(session_id, topic_id)
      
    return 'OK'
    
  
  owner = api.get_user_info(api.get_user_id(session_id))
  suggested_friends = [] # api.get_friend_suggestions(owner.to_dict())
  coworkers = [] # api.get_coworkers(session_id)
  
  archived = True if request.path.endswith('/archived') else False
  
  topics = api.get_messages(session_id, archived=archived)
  
  unread_messages = {}
  for i in api.get_unread_messages(session_id, archived=archived):
    if i and i.get('sender'):
      unread_messages[i['sender'].id] = i['unread_count']
    else:
      unread_messages[i['topic'].id] = i['unread_count']
      
  for message in topics:
    if message.topic_id:
      _id = message.topic_id
    elif message.sender.id == owner.id:
      _id = message.receiver.id
    else:
      _id = message.sender.id
    if unread_messages.has_key(_id):
      message.unread_count = unread_messages[_id]
    else:
      message.unread_count = 0

  if request.method == 'GET':
    return render_homepage(session_id, 'Messages',
                           suggested_friends=suggested_friends,
                           coworkers=coworkers,
                           topics=topics, 
                           user_id=user_id, topic_id=topic_id,
                           archived=archived,
                           view='messages')
  else:
    body = render_template('expanded_chatbox.html',
                           suggested_friends=suggested_friends,
                           coworkers=coworkers,
                           topics=topics, 
                           user_id=user_id, topic_id=topic_id,
                           archived=archived,
                           owner=owner)
    resp = Response(dumps({'body': body,
                           'title': 'Messages'}))
    return resp      


@app.route("/", methods=["GET"])
@line_profile
def home():
  hostname = request.headers.get('Host', '').split(':')[0]
  session_id = request.args.get('session_id')
  
  if hostname != settings.PRIMARY_DOMAIN:
    if not api.is_exists(db_name=hostname.replace('.', '_')):
      abort(404)
    
    if session_id:
      session.permanent = True
      session['session_id'] = request.args.get('session_id')
      return redirect('/news_feed')
  
  
    
  session_id = session.get("session_id")
  user_id = api.get_user_id(session_id)
  
  if not user_id:
    code = request.args.get('code')
    user_id = api.get_user_id(code)
    if user_id and not session_id:
      session['session_id'] = code
      owner = api.get_user_info(user_id)
      return render_template('profile_setup.html',
                             owner=owner,
                             code=code, user_id=user_id)
    
  if not session_id or not user_id:
    try:
      session.pop('session_id')
    except KeyError:
      pass
    
    if hostname != settings.PRIMARY_DOMAIN:
      return redirect('/sign_in')
    
    email = request.args.get('email')
    message = request.args.get('message')
    resp = Response(render_template('landing_page.html',
                                    email=email,
                                    message=message))
    
    back_to = request.args.get('back_to')
    if back_to:
      resp.set_cookie('redirect_to', back_to)
    
    return resp
  else:
    return redirect('/news_feed')
  
  
@app.route("/news_feed", methods=["GET", "OPTIONS"])
@app.route("/news_feed/page<int:page>", methods=["GET", "OPTIONS"])
@app.route('/archived', methods=['GET', 'OPTIONS'])
@app.route('/archived/page<int:page>', methods=['GET', 'OPTIONS'])
@app.route("/news_feed/archive_from_here", methods=["POST"])
@login_required
@line_profile
def news_feed(page=1):  
  session_id = session.get("session_id")
    
  if request.path.endswith('archive_from_here'):
    ts = float(request.args.get('ts', api.utctime()))
    api.archive_posts(session_id, ts)
    return 'Done'
    
    
  user_id = api.get_user_id(session_id)
  
  if user_id and request.cookies.get('redirect_to'):
    redirect_to = request.cookies.get('redirect_to')
    if redirect_to != request.url:
      resp = redirect(request.cookies.get('redirect_to'))
      resp.delete_cookie('redirect_to')
      return resp
  
  
  # Bắt user dùng facebook phải invite friends trước khi dùng ứng dụng
#  
#  if request.args.get('request') and request.args.get('to[0]'):
#    api.update_user_info(session_id, {'fb_request_sent': True})
#  
#  else:
#    user = api.get_user_info(user_id)
#    if not user.fb_request_sent:
#      return redirect('https://www.facebook.com/dialog/apprequests?app_id=%s' % settings.FACEBOOK_APP_ID \
#                      + '&message=Qua%20%C4%91%C3%A2y%20th%E1%BB%AD%20c%C3%A1i%20n%C3%A0o%20:-)&redirect_uri=https://www.jupo.com/')
#  
  
  #####
  
  
  filter = request.args.get('filter', 'default')
  app.logger.debug('session_id: %s' % session_id)
  
  
  view = 'news_feed'
  title = "Jupo"
  hostname = request.headers.get('Host').split(':')[0]
  if hostname != settings.PRIMARY_DOMAIN:
    network_info = api.get_network_info(hostname.replace('.', '_'))
    if network_info and network_info.has_key('name'):
      title = network_info['name']
  
  if filter == 'archived':
    feeds = api.get_archived_posts(session_id, page=page)
    category = 'archived'
  elif filter == 'email':
    feeds = api.get_emails(session_id, page=page)
    category = 'email'
  elif filter == 'all':
    feeds = api.get_feeds(session_id, page=page, 
                          include_archived_posts=True)
    category = None
#  elif '@' in filter:
#    feeds = api.get_emails(session_id, page)
  else:
    feeds = api.get_feeds(session_id, page=page, 
                          include_archived_posts=False)
    category = None
    
    
  owner = api.get_user_info(user_id)
  
  if request.method == "OPTIONS":
    if page > 1:
      posts = []
      for feed in feeds:
        if feed.id not in owner.unfollow_posts:
          posts.append(render(feed, "feed", owner, view)) 
      if len(feeds) == 0:
        posts.append(render_template('more.html', more_url=None))
      elif filter:
        posts.append(render_template('more.html', 
                                     more_url='/news_feed/page%d?filter=%s' \
                                     % (page+1, filter)))
      else:
        posts.append(render_template('more.html', 
                                     more_url='/news_feed/page%d' % (page+1)))
      
      return ''.join(posts)
    
    else:
      
      pinned_posts = api.get_pinned_posts(session_id) \
                     if filter == 'default' else None
      suggested_friends = api.get_friend_suggestions(owner.to_dict())
      coworkers = api.get_coworkers(session_id)
      browser = api.Browser(request.headers.get('User-Agent'))
      
      body = render_template('news_feed.html', 
                             owner=owner,
                             view=view, 
                             title=title, 
                             filter=filter,
                             browser=browser,
                             category=category,
                             coworkers=coworkers,
                             suggested_friends=suggested_friends,
                             pinned_posts=pinned_posts,
                             feeds=feeds)
      
      json = dumps({"body": body, 
                    "title": title})
            
      resp = Response(json, mimetype='application/json')
      
      
  else:  
    pinned_posts = api.get_pinned_posts(session_id) \
                   if filter == 'default' else None
    suggested_friends = api.get_friend_suggestions(owner.to_dict())
    coworkers = api.get_coworkers(user_id, limit=5)
    browser = api.Browser(request.headers.get('User-Agent'))
    
    resp = render_homepage(session_id, title,
                           view=view,
                           coworkers=coworkers,
                           filter=filter,
                           browser=browser,
                           category=category,
                           pinned_posts=pinned_posts,
                           suggested_friends=suggested_friends,
                           feeds=feeds)
    
  resp.delete_cookie('redirect_to')
  return resp


@app.route("/feed/new", methods=['POST'])
@app.route("/feed/<int:feed_id>", methods=['GET', 'OPTIONS'])
@app.route("/post/<int:feed_id>", methods=['GET'])
@app.route("/feed/<int:feed_id>/<action>", methods=["POST"])
@app.route("/feed/<int:feed_id>/<int:comment_id>/<action>", methods=["POST"])
@app.route("/feed/<int:feed_id>/starred", methods=["OPTIONS"])
@app.route("/feed/<int:feed_id>/<message_id>@<domain>", methods=["GET", "OPTIONS"])
@app.route("/feed/<int:feed_id>/likes", methods=["OPTIONS"])
@app.route("/feed/<int:feed_id>/read_receipts", methods=["OPTIONS"])
@app.route("/feed/<int:feed_id>/comments", methods=["OPTIONS"])
@app.route("/feed/<int:feed_id>/viewers", methods=["GET", "POST"])
@app.route("/feed/<int:feed_id>/reshare", methods=["GET", "POST"])
@line_profile
def feed_actions(feed_id=None, action=None, 
                 message_id=None, domain=None, comment_id=None):
  session_id = session.get("session_id")
  
#  if message_id:
#    message_id = '%s@%s' % (message_id, domain)
#    
#    # TODO: check permission
#    message = api.DATABASE[api.get_database_name(request)].stream.find_one({'message_id': message_id})
#    if not message:
#      thread = api.DATABASE.stream.find_one({'comments.message_id': message_id})
#      if thread:
#        comments = thread['comments']
#        for comment in comments:
#          if comment.get('message_id') == message_id:
#            message = comment
#            message['subject'] = thread['subject']
#            message['body'] = comment.get('html', comment.get('message'))
#            break
#      else:
#        abort(404)
#    else:
#      message['body'] = message.get('html', message.get('body'))
#      
#  
#    if request.method == 'OPTIONS':
#      message['id'] = feed_id
#      return dumps({'body': render_template('email.html', feed=message),
#                    'title': message['subject']})
#      return message
#    else:
#      return render_homepage(session_id, message['subject'],
#                             view='email', mode='view', feed=message)
  
  user_id = api.get_user_id(session_id)
  if not user_id:
    abort(400)
    
  utcoffset = request.cookies.get('utcoffset')
  if utcoffset:
    api.update_utcoffset(user_id, utcoffset)
  
  owner = api.get_user_info(user_id)
#  if not owner.id:
#    return redirect('/sign_in?continue=%s' % request.path)
  
  if request.path.endswith('new'):
    facebook_access_token = session.get('facebook_access_token', [None])[0]
    message = request.form.get('message')
    viewers = request.form.get('viewers')
    if viewers:
      viewers = viewers.split(',')
    else:
      viewers = []    
    
    attachments = request.form.get('attachments')
    if attachments:
      attachments = attachments.rstrip(',').split(',')
      attachments = list(set(attachments))
    else:
      attachments = []

    feed_id = api.new_feed(session_id, 
                           message, 
                           viewers, 
                           attachments,
                           facebook_access_token=facebook_access_token)
    feed = api.get_feed(session_id, feed_id)
    return render_template('feed.html', 
                           view=request.args.get('rel'),
                           feed=feed, owner=owner, hide_comments=True)
    
  elif request.path.endswith('/viewers'):
    if request.method == 'GET':
      feed = api.get_feed(session_id, feed_id)
      return render_template('viewers.html', feed=feed)
    else:
      viewers = request.form.get('viewers')
      viewers = viewers.split(',')
      
      api.set_viewers(session_id, feed_id, viewers)
      
      feed = api.get_feed(session_id, feed_id)
      return render_template('feed.html', 
                             owner=owner,
                             feed=feed)
    
  elif request.path.endswith('/reshare'):
    if request.method == 'GET':
      return render_template('reshare.html', feed_id=feed_id)
    else:
      viewers = request.form.get('to')
      viewers = viewers.split(',')
      app.logger.debug(viewers)
      
      api.reshare(session_id, feed_id, viewers)
      
      feed = api.get_feed(session_id, feed_id)
      return render_template('feed.html', 
                             view='discover',
                             owner=owner,
                             feed=feed)
      
  elif request.path.endswith('/starred'):
    feed = api.get_feed(session_id, feed_id)
    users = feed.starred_by    
    body = render_template('users.html', title='Starred', users=users)
    json = dumps({'body': body, 'title': 'Intelliview'})
    return Response(json, mimetype='application/json')
    
  elif request.path.endswith('/likes'):
    feed = api.get_feed(session_id, feed_id)
    users = feed.liked_by
    
    body = render_template('people_who_like_this.html',
                           owner=owner, users=users)
    json = dumps({'body': body, 'title': 'People who like this'})
    return Response(json, mimetype='application/json')  
    
  elif request.path.endswith('/read_receipts'):
    feed = api.get_feed(session_id, feed_id)
    read_receipts = feed.seen_by
    
    body = render_template('people_who_saw_this.html',
                           owner=owner, read_receipts=read_receipts)
    json = dumps({'body': body, 'title': 'People who saw this'})
    return Response(json, mimetype='application/json')  
    
  
  elif request.path.endswith('/comments'):
    limit = int(request.args.get('limit', 5))
    last_comment_id = int(request.args.get('last'))
    
    post = api.get_feed(session_id, feed_id)
    if not post.id:
      abort(400)
    
    comments = []
    for comment in post.comments:
      if comment.id == last_comment_id:
        break
      else:
        comments.append(comment)
    
    if len(comments) > limit:
      comments = comments[-limit:]
      
    html = render(comments, 'comment', 
                  owner, None, None, 
                  item=post, hidden=True)
    resp = {'html': html,
            'length': len(comments),
            'comments_count': post.comments_count}
    
    if comments[0].id != post.comments[0].id:
      resp['next_url'] = '/feed/%s/comments?last=%s' \
                          % (feed_id, comments[0].id)
      
    return Response(dumps(resp), mimetype='application/json')
  
  
  elif action == 'remove':
    group_id = request.args.get('group_id')
    api.remove_feed(session_id, feed_id, group_id=group_id)
    
  elif action == 'undo_remove':
    feed_id = api.undo_remove(session_id, feed_id)
    
  elif action == 'star':
    feed_id = api.star(session_id, feed_id)
    
  elif action == 'unstar':
    feed_id = api.unstar(session_id, feed_id)  
    
  elif action == 'pin':
    feed_id = api.pin(session_id, feed_id)  
    
  elif action == 'unpin':
    feed_id = api.unpin(session_id, feed_id)  
    
  elif action == 'archive':
    api.archive_post(session_id, feed_id)
    
  elif action == 'unarchive':
    api.unarchive_post(session_id, feed_id)
  
  elif action == 'remove_comment':
    api.remove_comment(session_id, comment_id, post_id=feed_id)
  
  elif action == 'update':
    message = request.args.get('msg').strip()
    api.update_post(session_id, feed_id, message)
    return 'OK'
    
  elif action == 'update_comment':
    message = request.form.get('message')
    api.update_comment(session_id, comment_id, message, post_id=feed_id)
    comment = '''{{ message | autolink | autoemoticon | nl2br | sanitize }}'''
    message = api.filters.sanitize_html(\
                  api.filters.nl2br(\
                      api.filters.autoemoticon(\
                          api.filters.autolink(message))))

    return message
      
  elif action == 'unfollow':
    feed_id = api.unfollow_post(session_id, feed_id)
      
  elif action == 'mark_as_task':
    api.mark_as_task(session_id, feed_id)
      
  elif action == 'mark_unresolved':
    api.mark_unresolved(session_id, feed_id)
      
  elif action == 'mark_as_read':
    api.mark_as_read(session_id, feed_id)
      
  elif action == 'comment':
    
    message = request.form.get('message', '')
    attachments = request.form.get('attachments')
    reply_to = request.form.get('reply_to')
    if reply_to.isdigit():
      reply_to = int(reply_to)
    else:
      reply_to = None  
    from_addr = request.form.get('from')
    app.logger.debug(from_addr) 
    
    if not message and not attachments:
      abort(403)
    
    app.logger.debug(attachments) 
    if attachments:
      attachments = attachments.rstrip(',').split(',')
      attachments = list(set(attachments))
    else:
      attachments = []

    info = api.new_comment(session_id, 
                           message, feed_id, attachments, 
                           reply_to=reply_to,
                           from_addr=from_addr)
    
    if not info:
      abort(400)
    
    item = {'id': feed_id}
    html = render_template('comment.html', 
                           comment=info,
                           prefix='feed',
                           item=item,
                           owner=owner)
    
    return html
    
  else:
    feed = api.get_feed(session_id, feed_id)
    if request.method == 'OPTIONS':
      body = render_template('news_feed.html',
                             view='news_feed',
                             mode='view',
                             owner=owner,
                             feed=feed)
      msg = filters.clean(feed.message)
      if not msg or \
        (msg and str(msg).strip()[0] == '{' and str(msg).strip()[-1] == '}'):
        title = ''
      else:
        title = msg if len(msg)<= 50 else msg[:50] + '...'
        title = title.decode('utf-8', 'ignore').encode('utf-8')
        
      json = dumps({'body': body, 'title': title})
      return Response(json, mimetype='application/json')
    else:
      if not session_id and feed is False:
        return redirect('/?back_to=%s' % request.path)
      
      if session_id and not feed.id:
        abort(404)
      
      image = description = None
      if feed.is_note():
        title = feed.details.title
        description = feed.details.content
        # TODO: insert image of post
      elif feed.is_file():
        title = feed.details.name
        description = feed.details.size
      else:
        
        msg = filters.clean(feed.message)
        if not msg or \
          (msg and str(msg).strip()[0] == '{' and str(msg).strip()[-1] == '}'):
          title = ''
        else:
          title = msg if len(msg)<= 50 else msg[:50] + '...'
          title = title.decode('utf-8', 'ignore').encode('utf-8')
            

        if feed.urls:
          url = feed.urls[0]
          description = feed.urls[0].description
          if url.img_src:
            image = url.img_src
          else:
            image = url.favicon
      if request.path.startswith('/post/') or not owner.id:
        return render_template('post.html',
#                                background='dark-bg', 
                               owner=owner,
                               mode='view',
                               title=title, description=description, image=image, feed=feed)
      else:
        return render_homepage(session_id, 
                               title=title, description=description, image=image,
                               view='feed', mode='view', feed=feed)
    
  return str(feed_id)


@csrf.exempt
@app.route('/hooks/<service>/<key>', methods=['POST'])
@app.route('/group/<int:group_id>/new_<service>_key')
def service_hooks(service, key=None, group_id=None):
  hostname = request.headers.get('Host')
  
  if group_id: # new key
    session_id = session.get('session_id')
    key = api.get_new_webhook_key(session_id, group_id, service)
    return 'http://%s/hooks/%s/%s' % (hostname, service, key)
  
  if service == 'gitlab':
    feed_id = api.new_hook_post(service, key, request.data)
  elif service == 'github':
    feed_id = api.new_hook_post(service, key, request.form.get('payload'))
  return str(feed_id)  

@app.route('/events', methods=['GET', 'OPTIONS'])
def events():
  session_id = session.get("session_id")
  events = api.get_events(session_id, as_feeds=True)
  if request.method == 'GET':
    return render_homepage(session_id, 'Events',
                           view='events',
                           events=events)
  else:
    owner = api.get_owner_info(session_id)
    body = render_template('events.html', events=events, owner=owner)
    return dumps({'body': body, 'title': 'Events'})



@app.route('/event/new', methods=['OPTIONS', 'POST'])
@app.route('/event/<int:event_id>', methods=['GET', 'OPTIONS'])
@app.route('/event/<int:event_id>/mark_as_read', methods=['GET', 'POST'])
@app.route('/<int:group_id>/events', methods=['GET', 'POST'])
def event(event_id=None, group_id=None):
  session_id = session.get("session_id")
  if request.path == '/event/new':
    group_id = request.args.get('group_id')
    name = request.form.get("name")
    if not name:  # not submit
      if group_id:
        group = api.get_group_info(session_id, group_id)
      else:
        group = None
      body = render_template('event.html', group=group)
      return dumps({'body': body})
    
    when = request.form.get('when')
    when = strptime(when, "%a %d, %B %Y - %I:%M%p")
    when = mktime(when)
    
    where = request.form.get('where')
    details = request.form.get('details')
    viewers = request.form.get('viewers')
    if viewers:
      viewers = viewers.split(',')
    event_id = api.new_event(session_id, name, when, where, None, details, viewers)
    event = api.get_event(session_id, event_id)
    body = render_template('event.html', 
                           event=event)
    return dumps({'body': body,
                  'reload': True})
  elif group_id:
    events = api.get_events(session_id, group_id)
    pass
  elif event_id:
    if request.path.endswith('mark_as_read'):
      api.mark_as_read(session_id, event_id)
      return 'Done'
    event = api.get_event(session_id, event_id)
    body = render_template('event.html', event=event)
    return dumps({'body': body})
    
  else:
    event = api.get_events(session_id)

  
@app.route("/files", methods=['GET', 'OPTIONS'])
@login_required
@line_profile
def files():
  session_id = session.get("session_id")
  owner = api.get_owner_info(session_id)
  title = "Files"
  files = api.get_files(session_id) 
  attachments = api.get_attachments(session_id) 
  if request.method == 'OPTIONS':
    body = render_template('files.html', 
                           view='files', 
                           owner=owner,
                           files=files,
                           attachments=attachments)
    return dumps({'body': body, 
                  'title': 'Files'})
  else:
    return render_homepage(session_id, title,
                           view='files', 
                           files=files, 
                           attachments=attachments)
    
  

@app.route("/attachment/new", methods=["POST"])
@app.route("/attachment/<int:attachment_id>")
@app.route("/attachment/<int:attachment_id>.png")
@app.route("/attachment/<int:attachment_id>.jpg")
@app.route("/attachment/<int:attachment_id>/<action>", methods=["POST"])
def attachment(attachment_id=None, action=None):
  session_id = session.get("session_id")
  if request.path.endswith('new'):
    file = request.files.get('file')
    filename = file.filename
    attachment_id = api.new_attachment(session_id, 
                                 file.filename, 
                                 file.stream.read())
    info = api.get_attachment_info(attachment_id)
    info = {'html': render_template('attachment.html', attachment=info),
            'attachment_id': str(attachment_id)}
    json = dumps(info)
    return Response(json, mimetype='application/json')

  
  elif action == 'remove':
    api.remove_attachment(session_id, attachment_id)
    return str(attachment_id)
  else:
    attachment = api.get_attachment(attachment_id)
    post_id = request.args.get('rel')
    viewers = []
    if post_id:
      post = api.get_feed(session_id, int(post_id))
      if (post and not post.id) or not post:
        abort(400)
      comments = post.to_dict().get('comments')
      if attachment_id in post.attachment_ids:
        viewers = post.viewer_ids
      elif comments:
        for comment in comments:
          if attachment_id in comment.get('attachments', []):
            viewers = post.viewer_ids
            break
      else:
        abort(403, 'Permission Denied')
    else:
      viewers = [api.get_attachment_info(attachment_id).owner.id]

      
    if isinstance(attachment, unicode) or isinstance(attachment, str):
      s3_url = attachment
      return redirect(s3_url, code=301)
    
    
    if not attachment:
      abort(404, 'File not found')
      
    filedata = attachment.read()
    filename = attachment._filename
    
    resp = Response(filedata)
    
    name = request.args.get('name', request.args.get('filename'))
    content_type = attachment.content_type \
                   if attachment.content_type \
                   else 'application/octet-stream'
    if not name and not content_type.startswith('image/'):
      name = filename
    if name:
      resp.headers['Content-Disposition'] = str('attachment; filename="%s"' % name)
      resp.headers['Content-Type'] = guess_type(name)[0]
    else:
      resp.headers['Content-Type'] = guess_type(filename)[0]
    
    return resp
  

@app.route("/img/<int:attachment_id>.png")
@app.route("/img/<int:attachment_id>.jpg")
@app.route("/img/<size>/<int:attachment_id>.png")
@app.route("/img/<size>/<int:attachment_id>.jpg")
def profile_pictures(attachment_id, size='60'):
  try:
    info = api.get_attachment_info(attachment_id)
    if info.md5 and api.is_s3_file(info.md5 + '_%s.jpg' % size):
      url = 'https://%s.s3.amazonaws.com/%s_%s.jpg' % (settings.S3_BUCKET_NAME, info.md5, size)
      return redirect(url, code=301)
    
    data = api.get_file_data(attachment_id)
    if not data:
      return redirect('http://www.jupo.com/public/images/avatar.96.gif')
    if size.isdigit():
      size = int(size)
      filedata = zoom(data, size, size)
    else:
      width, height = size.split('_')
      filedata = zoom(data, int(width), int(height))
        
    domain = request.headers.get('Host')
    db_name = domain.lower().strip().replace('.', '_')
    api.move_to_s3_queue.enqueue(api.move_to_s3, '%s_%s.jpg|%s|%s' \
                                 % (api.hashlib.md5(data).hexdigest(), 
                                    str(size), 'image/jpeg', filedata),
                                 db_name)
    return Response(filedata, mimetype='image/jpeg')
  
  except api.NoFile:  # 'NoneType' object has no attribute 'get'
    return redirect('http://www.jupo.com/public/images/avatar.96.gif')
#    abort(404, 'File not found')
    


@app.route("/file/new", methods=["POST"])
@app.route("/file/<int:file_id>", methods=["GET", "POST", "OPTIONS"])
@app.route("/file/<int:file_id>/<action>", methods=["POST"])
def file(file_id=None, action=None, size=None):
  session_id = session.get("session_id")
  owner = api.get_owner_info(session_id)
  if request.path == '/file/new':
    attachments = request.form.get('attachments')
    attachments = [i for i in attachments.split(',') if i]
    
    viewers = request.form.get('viewers')
    if viewers:
      viewers = viewers.split(',')
    else:
      viewers = []
    
    blocks = []
    for attachment in attachments:
      file_id = api.new_file(session_id, attachment, viewers)
      file = api.get_file_info(session_id, file_id)
      blocks.append(render_template('file.html', 
                                    owner=owner,
                                    file=file))
  
    return ''.join(blocks)
  
  elif action == 'mark_as_read':
    api.mark_as_read(session_id, file_id)
    return 'Done'
    
  elif action == 'comment':
    message = request.form.get('message')
    info = api.new_comment(session_id, message, file_id)
          
    return render_template('comment.html', 
                           comment=info,
                           prefix='stream',
                           owner=owner)
  elif action == 'update':
    file = request.files.get('file')
    filename = file.filename
    attachment_id = api.new_attachment(session_id, 
                                       file.filename, 
                                       file.stream.read())
    api.update_file(session_id, file_id, attachment_id)
    info = api.get_file_info(session_id, file_id)
    
    info = {'html': render_template('file.html', 
                                    owner=owner,
                                    file=info)}
    return Response(dumps(info), mimetype='application/json')
  
  elif action == 'rename':
    new_name = request.form.get('name')
    if not new_name:
      abort(400)
    api.rename_file(session_id, file_id, new_name)
    info = api.get_file_info(session_id, file_id)
    
    return render_template('file.html', owner=owner,file=info)
    
  
  else:
    file = api.get_file_info(session_id, file_id)
    body = render_template('files.html',
                           mode='view',
                           view='files',
                           owner=owner,
                           file=file)
      
    return dumps({'body': body,
                  'title': file.name})



@app.route('/set', methods=["POST", "HEAD"])  # HEAD for websocket set status
def change_status():
  session_id = request.args.get('session_id')
  if not session_id:
    session_id = session.get("session_id")
    if not session_id:
      abort(401, 'Authentication credentials were missing')
  status = request.args.get('status') 
  is_success = api.set_status(session_id, status)
  if is_success:
    return 'OK'
  else:
    abort(401, 'Authentication credentials were incorrect.')  



# Notifications ----------------------------------------------------------------

@app.route('/notifications', methods=['GET', 'OPTIONS'])
@login_required
@line_profile
def notifications():
  session_id = session.get("session_id")
    
  notifications = api.get_notifications(session_id)
  unread_messages = api.get_unread_messages(session_id)
  unread_messages_count = len(unread_messages)
  
  hostname = request.headers.get('Host')
  network = api.get_network_info(hostname.replace('.', '_'))
    
  if request.method == 'OPTIONS':
    owner = api.get_owner_info(session_id)
    body = render_template('notifications.html',
                           owner=owner, 
                           network=network,
                           unread_messages=unread_messages,
                           notifications=notifications)
    resp = {'body': body,
            'title': 'Notifications'}
    
    
    unread_count = api.get_unread_notifications_count(session_id) \
                 + unread_messages_count
    
#     if unread_count:
#       #  mark as read luôn các notifications không quan trọng
#       api.mark_notification_as_read(session_id, type='like')
#       api.mark_notification_as_read(session_id, type='add_contact')
#       api.mark_notification_as_read(session_id, type='google_friend_just_joined')
#       api.mark_notification_as_read(session_id, type='facebook_friend_just_joined')
#       api.mark_all_notifications_as_read(session_id)
      
    resp['unread_notifications_count'] = unread_count
    return dumps(resp)
  else:
    return render_homepage(session_id, 'Notifications',
                           notifications=notifications,
                           network=network,
                           unread_messages=unread_messages,
                           view='notifications')


@app.route('/notification', methods=['GET', 'POST'])
@app.route('/notification/<int:ref_id>-comments', methods=['GET', 'POST'])
@app.route('/notification/<int:id>', methods=['GET', 'POST'])
@app.route('/notification/<int:id>/mark_as_read', methods=['GET', 'POST'])
@app.route('/post/<int:post_id>/mark_as_read', methods=['GET', 'POST'])
@app.route('/notifications/mark_as_read', methods=['GET', 'POST'])
@login_required
def notification(id=None, ref_id=None, post_id=None):
  app.logger.debug(id)
  session_id = session.get("session_id")
  
  
  if request.path.endswith('mark_as_read'):
    if id:
      api.mark_notification_as_read(session_id, id)
      return 'Done'
    else:
      api.mark_all_notifications_as_read(session_id)
  
  if post_id:
    ref_id = post_id
  
  if id:
    api.mark_notification_as_read(session_id, id)
  elif ref_id:
    api.mark_notification_as_read(session_id,
                                  ref_id=ref_id)
  else:
    api.mark_notification_as_read(session_id, 
                                  type='conversation',
                                  ts=api.utctime())
  
  unread_notification_count = api.get_unread_notifications_count(session_id)
  unread_messages = api.get_unread_messages(session_id)
  
  return str(unread_notification_count + len(unread_messages))


@app.route('/feeds/<int:user_id>')
def atom_feeds(user_id):
  owner = api.get_user_info(user_id)
  feeds = api.get_feeds(owner.session_id, limit=100)
  
  resp = Response(render_template('news_feed.atom', owner=owner, feeds=feeds))
  resp.headers['Content-Type'] = 'application/atom+xml'
  return resp


@app.route('/like/<int:item_id>', methods=['GET', 'POST'])
@app.route('/unlike/<int:item_id>', methods=['GET', 'POST'])
@login_required
def like(item_id):
  session_id = session.get("session_id")
  post_id = request.args.get('post_id')
  if post_id:
    post_id = int(post_id)
  else:
    post_id = item_id
    
  if request.path.startswith('/like/'):
    is_ok = api.like(session_id, item_id, post_id)
  else:
    is_ok = api.unlike(session_id, item_id, post_id)
  if is_ok:  
    return 'OK'
  else:
    return 'Error'

#===============================================================================
# _Collaborate
#===============================================================================
@app.route('/_clear_cache')
def _clear_cache():
  filename = request.args.get('filename').lower().strip()
  cache.delete('file:%s' % filename.lower().strip())
  cache.delete('file:%s:last_updated' % filename)
  return 'Done'
  

@app.route('/_update', methods=['GET', 'POST'])
def _update():
  ts = content = None
  if request.method == 'GET':
    key = None
    filename = 'main.js'
  else:
    key = request.form.get('key')
    filename = request.form.get('filename')
    if key == '3.' and filename.endswith('.js'):
      ts = int(api.utctime())
      content = request.form.get('content')
      cache.set('file:%s' % filename.lower().strip(), content, None)
      cache.set('file:%s:last_updated' % filename, ts, None)
      
  if not ts:
    ts = cache.get('file:%s:last_updated' % filename)
    ts = ts if ts else 0
  
  if not content:
    content = cache.get('file:%s' % filename)
  
  return render_template('_update.html', key=key, 
                         ts=api.datetime.fromtimestamp(ts).isoformat(),
                         content=content, filename=filename)



#===============================================================================
# Run App
#===============================================================================

if 'jupo.com' in settings.PRIMARY_DOMAIN:
  @app.before_request
  def redirect_if_not_play_jupo():
    """Redirect www.jupo.com or jupo.com to play.jupo.com"""
    if request.headers.get('Host') in ['www.jupo.com', 'jupo.com']:
      url = 'http://play.jupo.com%s' % request.path
      if request.environ.get('QUERY_STRING'):
        url += '?' + request.environ.get('QUERY_STRING')
      return redirect(url, code=301)
  
  
def run_app(debug=False):
    
  from cherrypy import wsgiserver
    
  settings.DEBUG = debug
  
  app.debug = settings.DEBUG
  
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
  
  toolbar = flask_debugtoolbar.DebugToolbarExtension(app)
  

  
  #server = wsgiserver.CherryPyWSGIServer(('0.0.0.0', 8888), app)
  server = wsgiserver.CherryPyWSGIServer(('0.0.0.0', 9000), app)
  try:
    print 'Serving HTTP on 0.0.0.0 port 8888...'
    server.start()
  except KeyboardInterrupt:
    print '\nGoodbye.'
    server.stop()
  
  
if __name__ == "__main__":
  run_app(debug=False)





