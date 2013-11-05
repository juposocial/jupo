#! coding: utf-8
# pylint: disable-msg=W0311, W0611, E1103, E110

from raven.contrib.flask import Sentry
 
from flask import (request, render_template, 
                   redirect, abort, session, Response)
from flask.ext.seasurf import SeaSurf
from flask.ext.assets import Bundle, Environment as WebAssets
from werkzeug.wrappers import Request, BaseRequest
from werkzeug.contrib.securecookie import SecureCookie

from datetime import datetime
from mimetypes import guess_type
from simplejson import dumps, loads

from jinja2 import Environment
from werkzeug.contrib.cache import MemcachedCache

import requests
import werkzeug.serving

import os
import api
import settings
from app import CURRENT_APP, render


requests.adapters.DEFAULT_RETRIES = 3

app = CURRENT_APP
  
assets = WebAssets(app)

if settings.SENTRY_DSN:
  sentry = Sentry(app, dsn=settings.SENTRY_DSN, logging=False)
  


@app.route('/public/<path:filename>')
def public_files(filename):
  path = os.path.join(os.path.dirname(__file__), 'public', filename)
  if not os.path.exists(path):
    abort(404, 'File not found')
  filedata = open(path).read()  
      
  resp = Response(filedata)
  resp.headers['Content-Length'] = len(filedata)
  resp.headers['Content-Type'] = guess_type(filename)[0]
  resp.headers['Cache-Control'] = 'max-age=0'
  resp.headers['Expires'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
  return resp



@app.route('/oauth/google')
def google_login():
  network = request.args.get('network', 'jupo.com') 
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
  session['session_id'] = session_id
  session['network'] = network
  session['utcoffset'] = utcoffset
  session.permanent = True
  
  # Get user info
  user_id = api.get_user_id(session_id, db_name=db_name)
  user = api.get_user_info(user_id, db_name=db_name)
  groups = []
  for group in api.get_groups(session_id, db_name=db_name, limit=5):
    groups.append({'name': group.name,
                   'link': '/group/%s' % group.id})
  data = {'id': user_id,
          'name': user.name,
          'avatar': user.avatar,
          'email': user.email,
          'groups': groups,
          'access_token': session.serialize(),
          'token_type': 'session',
          'unread_notifications': unread_notifications}
  
  return render_template('mobile/update_ui.html', data=dumps(data))
  
@app.route('/get_user_info')
def get_user_info():
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
      
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
    
  session_id = data.get('session_id')
  network = data.get('network')
  utcoffset = data.get('utcoffset')

  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  user_id = api.get_user_id(session_id, db_name=db_name)
  user = api.get_user_info(user_id, db_name=db_name)
  groups = []
  for group in api.get_groups(session_id, db_name=db_name):
    groups.append({'name': group.name,
                   'link': '/group/%s' % group.id})
    
  data = {'id': user.id,
          'name': user.name,
          'avatar': user.avatar,
          'email': user.email,
          'utcoffset': utcoffset,
          'groups': groups}
  
  resp = Response(dumps(data), mimetype='application/json')
  return resp

@app.route('/user/<int:user_id>', methods=['GET', 'OPTIONS'])
@app.route('/user/<int:user_id>/page<int:page>', methods=['GET', 'OPTIONS'])
@app.route('/user/<int:user_id>/<action>', methods=['GET'])
def user(user_id=None, page=1, action=None):
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
      
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
  
  session_id = data.get('session_id')
  network = data.get('network')
#   utcoffset = data.get('utcoffset')

  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  user = api.get_user_info(user_id, db_name=db_name)

  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)

  owner = api.get_user_info(user_id, db_name=db_name)
    
  if action == 'info':
    return render_template('mobile/user_info.html', user=user, owner=owner)
  elif action == 'follow':
    api.follow(session_id, user_id)
    return 'OK'
  elif action == 'unfollow':
    api.unfollow(session_id, user_id)
    return 'OK'
  
  
  view = 'view'
  mode = 'view'
  title = user.name
  if not session_id or owner.id == user.id:
    feeds = api.get_public_posts(user_id=user.id, page=page,
                                 db_name=db_name)
  else:
    feeds = api.get_user_posts(session_id, user_id, 
                               page=page, db_name=db_name)
  if page == 1:
    return render_template('mobile/user.html', view=view, 
                                               user=user,
                                               owner=owner,
                                               title=title, 
                                               settings=settings,
                                               feeds=feeds)
  else:
    posts = [render(feeds, 'feed', owner,
                    viewport='view', mode=mode, mobile=True)]
    if len(feeds) != 5:
      posts.append(render_template('more.html', more_url=None))
    else:
      posts.append(render_template('more.html',
                                   more_url='/user/%s/page%d' \
                                   % (user_id, page+1)))
    return ''.join(posts)

@app.route("/feed/<int:feed_id>/<action>", methods=["GET", "POST"])
def feed_actions(feed_id=None, action=None,
                 message_id=None, domain=None, comment_id=None):
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)

    data = SecureCookie.unserialize(authorization.split()[-1],
                                    settings.SECRET_KEY)
    if not data:
      abort(401)

  session_id = data.get('session_id')
  network = data.get('network')
  db_name = '%s_%s' % (network.replace('.', '_'),
                       settings.PRIMARY_DOMAIN.replace('.', '_'))

  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)

  owner = api.get_user_info(user_id, db_name=db_name)
  if action == 'comment':
    message = request.form.get('message', '')
    if not message:
      abort(403)
    reply_to = []
    attachments = []
    from_addr = []
    info = api.new_comment(session_id,
                           message, feed_id, attachments,
                           reply_to=reply_to,
                           from_addr=from_addr,
                           db_name=db_name)

    if not info:
      abort(400)

    item = {'id': feed_id}
    html = render_template('comment.html',
                           comment=info,
                           prefix='feed',
                           item=item,
                           owner=owner)

    return html


@app.route('/menu')
def menu():
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
      
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
    
  session_id = data.get('session_id')
  network = data.get('network')
#   utcoffset = data.get('utcoffset')

  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))

  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)
  
  owner = api.get_user_info(user_id, db_name=db_name)
  
  return render_template('mobile/menu.html', owner=owner)
  
  
@app.route('/news_feed', methods=['GET', 'OPTIONS'])
@app.route('/news_feed/page<int:page>', methods=['GET', 'OPTIONS'])
@app.route('/feed/<int:feed_id>', methods=['GET', 'OPTIONS'])
def news_feed(page=1, feed_id=None):
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
       
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
     
  session_id = data.get('session_id')
  network = data.get('network')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))

  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)
  
  owner = api.get_user_info(user_id, db_name=db_name)
  
  if feed_id:
    mode = 'view'
    title = 'Post'
    feeds = [api.get_feed(session_id, feed_id, db_name=db_name)]
  else:
    mode = None
    title = 'News Feed'
    feeds = api.get_feeds(session_id, page=page, db_name=db_name)
  
  if request.method == 'GET':
    return render_template('mobile/news_feed.html', owner=owner,
                                                    mode=mode,
                                                    title=title, 
                                                    view='news_feed', 
                                                    settings=settings,
                                                    feeds=feeds)
  else:   
    posts = [render(feeds, "feed", owner, 
                    viewport='news_feed', mode=mode, mobile=True)]
    if len(feeds) != 5:
      posts.append(render_template('more.html', more_url=None))
    else:
      posts.append(render_template('more.html', 
                                   more_url='/news_feed/page%d' % (page+1)))
    return ''.join(posts)
  

@app.route("/everyone", methods=['GET', 'OPTIONS'])
@app.route("/everyone/page<int:page>", methods=["GET", "OPTIONS"])
@app.route("/group/<int:group_id>", methods=['GET', 'OPTIONS'])
@app.route("/group/<int:group_id>/<action>")
@app.route("/groups")
def group(group_id='public', action='group', page=1):
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
      
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
    
  session_id = data.get('session_id')
  network = data.get('network')
#   utcoffset = data.get('utcoffset')

  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)
  owner = api.get_user_info(user_id, db_name=db_name)
  
  if request.path.startswith('/groups'):
    groups = api.get_groups(session_id, db_name=db_name)
    return render_template('mobile/groups.html', view='groups',
                                                 owner=owner,
                                                 groups=groups)
    
  
  group = api.get_group_info(session_id, group_id, db_name=db_name)
  
  if action == 'info':
    return render_template('mobile/group_info.html', group=group, owner=owner)
  elif action == 'follow':
    api.join_group(session_id, group_id)
    return 'OK'
  elif action == 'unfollow':
    api.leave_group(session_id, group_id)
    return 'OK'
  
  if not group.id:
    abort(401)
    
  if group_id == 'public':
    feeds = api.get_public_posts(session_id, page=page, db_name=db_name)
  else:
    feeds = api.get_feeds(session_id, group_id,
                          page=page, db_name=db_name)
  
  return render_template('mobile/group.html', 
                          feeds=feeds, 
                          group=group,
                          owner=owner,
                          settings=settings,
                          request=request,
                          view='group')

@app.route('/networks', methods=['GET', 'POST'])
@app.route('/network/<domain>', methods=['GET', 'POST'])
def network(domain=None):
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
       
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
     
  session_id = data.get('session_id')
  network = data.get('network')
  utcoffset = data.get('utcoffset')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)
  owner = api.get_user_info(user_id, db_name=db_name)
  
  if request.path.startswith('/networks'):
    return render_template('mobile/networks.html', 
                           current_network=network,
                           owner=owner)
  
  if not domain:
    abort(401)
  
  db_name = domain.replace('.', '_')
  network = api.get_network_by_current_hostname(domain)
  session_id = api.sign_in_with_google(email=owner.email, 
                                       name=owner.name, 
                                       gender=owner.gender, 
                                       avatar=owner.avatar, 
                                       link=owner.link, 
                                       locale=owner.locale, 
                                       verified=owner.verified,
                                       google_contacts=owner.google_contacts,
                                       db_name=db_name)
  if not session_id:
    abort(500)
  
  unread_notifications = api.get_unread_notifications_count(session_id,
                                                            db_name=db_name)
  session['session_id'] = session_id
  session['network'] = network
  session['utcoffset'] = utcoffset
  session.permanent = True
   
  # Get user info
  user_id = api.get_user_id(session_id, db_name=db_name)
  user = api.get_user_info(user_id, db_name=db_name)
  groups = []
  for group in api.get_groups(session_id, db_name=db_name, limit=5):
    groups.append({'name': group.name,
                   'link': '/group/%s' % group.id})
  data = {'id': user_id,
          'name': user.name,
          'avatar': user.avatar,
          'email': user.email,
          'groups': groups,
          'access_token': session.serialize(),
          'token_type': 'session',
          'unread_notifications': unread_notifications}
   
   
  return api.b64encode(dumps(data))

  
@app.route('/like/<int:item_id>', methods=['GET', 'POST'])
@app.route('/unlike/<int:item_id>', methods=['GET', 'POST'])
def like(item_id):
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
       
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
     
  session_id = data.get('session_id')
  network = data.get('network')
  utcoffset = data.get('utcoffset')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)
   
  owner = api.get_user_info(user_id, db_name=db_name)
  post_id = item_id
    
  if request.path.startswith('/like/'):
    is_ok = api.like(session_id, item_id, 
                     post_id, db_name=db_name)
  else:
    is_ok = api.unlike(session_id, item_id, post_id,
                       db_name=db_name)
  if is_ok:  
    return 'OK'
  else:
    return 'Error'  

  
@app.route('/notifications', methods=['GET', 'OPTIONS'])
def notifications():
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
      
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
    
  session_id = data.get('session_id')
  network = data.get('network')
#   utcoffset = data.get('utcoffset')

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
                         request=request,
                         notifications=notifications)
  
  
@app.route('/notification/<int:notification_id>')
@app.route('/notification/<int:ref_id>-comments')
def notification(notification_id=None, ref_id=None):
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
      
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
    
  session_id = data.get('session_id')
  
  
  if notification_id:
    api.mark_notification_as_read(session_id, notification_id)
  elif ref_id:
    api.mark_notification_as_read(session_id, ref_id=ref_id)
  
  return redirect(request.args.get('continue'))


@app.route('/sidebar')
def sidebar():  
  if session and session.get('session_id'):
    data = session
  else:
    authorization = request.headers.get('Authorization')
    if not authorization or not authorization.startswith('session '):
      abort(401)
       
    data = SecureCookie.unserialize(authorization.split()[-1], 
                                    settings.SECRET_KEY)
    if not data:
      abort(401)
     
  session_id = data.get('session_id')
  network = data.get('network')
  db_name = '%s_%s' % (network.replace('.', '_'), 
                       settings.PRIMARY_DOMAIN.replace('.', '_'))
  
  user_id = api.get_user_id(session_id, db_name=db_name)
  if not user_id:
    abort(401)
   
  owner = api.get_user_info(user_id, db_name=db_name)
  return render_template('mobile/sidebar.html', owner=owner)


if __name__ == "__main__":
  
  @werkzeug.serving.run_with_reloader
  def run_app(debug=True):
      
    from cherrypy import wsgiserver
      
    app.debug = debug
    
    server = wsgiserver.CherryPyWSGIServer(('0.0.0.0', 9009), app)
    
    try:
      print 'Serving HTTP on 0.0.0.0 port 9009...'
      server.start()
    except KeyboardInterrupt:
      print '\nGoodbye.'
      server.stop()
  
  
  run_app(debug=True)


