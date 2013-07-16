#! coding: utf-8
# pylint: disable-msg=W0311, E0611, E1101
# @PydevCodeAnalysisIgnore

import os
import re
import sys
import smaz
import fcntl
import struct
import socket
import base64
import hashlib
import logging
import calendar
import requests
import mimetypes

from os import urandom
from urllib import quote
from random import shuffle
from goose import Goose
from smtplib import SMTP
from unidecode import unidecode
from email.message import Message as EmailMsg
from email.header import Header
from email.MIMEText import MIMEText
from base64 import b64encode, b64decode
from lxml.html.diff import htmldiff
from itertools import izip
from uuid import uuid4, UUID
from string import capwords
from urllib2 import urlopen
from simplejson import dumps
from time import mktime
from datetime import datetime, timedelta
from httplib import CannotSendRequest
from pyelasticsearch import ElasticSearch, ElasticHttpNotFoundError
from diff_match_patch import diff_match_patch
from flask_debugtoolbar_lineprofilerpanel.profile import line_profile

from lib import cache
from lib import encode_url
from lib.url import extract_urls
from lib.hot_ranking import get_score
from lib.pbkdf2 import pbkdf2_bin # From https://github.com/mitsuhiko/python-pbkdf2

from gridfs import GridFS, NoFile
from bson.binary import Binary
from bson.objectid import ObjectId
from gevent import spawn, joinall
from pymongo import MongoClient as MongoDB
from pymongo.son_manipulator import SON

from redis import Redis, ConnectionPool
from memcache import Client as Memcached
from jinja2 import Environment, FileSystemLoader

from boto.s3.key import Key
from boto.s3.connection import S3Connection
from rq import Queue, use_connection
from validate_email import validate_email

from flask import request

try:
  from collections import OrderedDict as odict
except ImportError:
  from ordereddict import OrderedDict as odict


from models import (User, Group, Browser,
                    Comment, Feed, File, Note,
                    Version, Notification, Attachment, Reminder,
                    URL, Result, Event, Message, Topic)

import app
import filters
import settings

requests.adapters.DEFAULT_RETRIES = 3
months = dict((k,v) for k,v in enumerate(calendar.month_abbr)) 

# switch from the default ASCII to UTF-8 encoding
reload(sys)
sys.setdefaultencoding("utf-8")


DATABASE = MongoDB(settings.MONGOD_SERVERS, use_greenlets=True)
DATABASE['global'].user.ensure_index('email', background=True)
DATABASE['global'].spelling_suggestion.ensure_index('keyword', background=True)

INDEX = ElasticSearch('http://%s/' % settings.ELASTICSEARCH_SERVER)

host, port = settings.REDIS_SERVER.split(':')
FORGOT_PASSWORD = Redis(host=host, port=int(port), db=1)


if settings.AWS_KEY and settings.S3_BUCKET_NAME:
  s3_conn = S3Connection(settings.AWS_KEY, settings.AWS_SECRET, is_secure=False)
  BUCKET = s3_conn.get_bucket(settings.S3_BUCKET_NAME)
else:
  BUCKET = None

goose = Goose()
dmp = diff_match_patch()

host, port = settings.REDIS_PINGPONG_SERVER.split(':')
PINGPONG = Redis(host=host, port=int(port), db=0)

host, port = settings.REDIS_PUBSUB_SERVER.split(':')
pool = ConnectionPool(host=host, port=int(port), db=0)
PUBSUB = Redis(connection_pool=pool)

host, port = settings.REDIS_TASKQUEUE_SERVER.split(':')
TASKQUEUE = Redis(host=host, port=int(port), db=0)

use_connection(TASKQUEUE)
push_queue = Queue('push')
index_queue = Queue('index')
crawler_queue = Queue('urls')
invite_queue = Queue('invite')
send_mail_queue = Queue('send_mail')
move_to_s3_queue = Queue('move_to_s3')
notification_queue = Queue('notification')


def send_mail(to_addresses, subject=None, body=None, mail_type=None, 
              user_id=None, post=None, db_name=None, **kwargs):
  if not settings.SMTP_HOST:
    return False
  
  if not db_name:
    db_name = get_database_name()
    
  domain = db_name.replace('_', '.')

  if mail_type == 'thanks':    
    subject = 'Thanks for Joining the Jupo Waiting List'
    template = app.CURRENT_APP.jinja_env.get_template('email/thanks.html')
    body = template.render()
    
  elif mail_type == 'invite':
    if kwargs.get('group_name'):
      subject = "%s has invited you to %s" % (kwargs.get('username'), 
                                              kwargs.get('group_name'))
    else:
      subject = "%s has invited you to Jupo" % (kwargs.get('username'))
      
    template = app.CURRENT_APP.jinja_env.get_template('email/invite.html')
    body = template.render(domain=domain, **kwargs)
    
  elif mail_type == 'forgot_password':
    subject = 'Your password on Jupo'
    template = app.CURRENT_APP.jinja_env.get_template('email/reset_password.html')
    body = template.render(email=to_addresses, domain=domain, **kwargs)
    
  elif mail_type == 'welcome':
    subject = 'Welcome to Jupo!'
    body = None
    
  elif mail_type == 'mentions':
    user = get_user_info(user_id, db_name=db_name)
    post = Feed(post, db_name=db_name)
    subject = '%s mentioned you in a comment.' % user.name
    template = app.CURRENT_APP.jinja_env.get_template('email/new_comment.html')
    body = template.render(domain=domain, user=user, post=post)
    
  elif mail_type == 'new_post':
    user = get_user_info(user_id, db_name=db_name)
    post = Feed(post, db_name=db_name)
    subject = '%s shared a post with you' % user.name
    template = app.CURRENT_APP.jinja_env.get_template('email/new_post.html')
    body = template.render(domain=domain, email=to_addresses, user=user, post=post)
    
  elif mail_type == 'new_comment':
    user = get_user_info(user_id, db_name=db_name)
    post = Feed(post, db_name=db_name)
    if post.is_system_message():
      if post.message.get('action') == 'added':
        subject = 'New comment to "%s added %s to %s group."' \
                % (post.owner.name, 
                   post.message.user.name, 
                   post.message.group.name)
      elif post.message.get('action') == 'created':
        subject = 'New comment to "%s created %s group."' \
                % (post.owner.name, 
                   post.message.group.name)
      else:
        subject = "New comment to %s's post" % (post.owner.name)
    else:
      post_msg = filters.clean(post.message)
      if len(post_msg) > 30:
        subject = "New comment to %s's post: \"%s\"" \
                % (post.owner.name, post_msg[:30] + '...')
        subject = subject.decode('utf-8', 'ignore').encode('utf-8') 
      else:
        subject = "New comment to %s's post: \"%s\"" \
                % (post.owner.name, post_msg) 
    
    template = app.CURRENT_APP.jinja_env.get_template('email/new_comment.html')
    body = template.render(domain=domain, email=to_addresses, user=user, post=post)
    
  
  if to_addresses and subject and body:
  
    msg = MIMEText(body, 'html', _charset="UTF-8")
    msg['Subject']= Header(subject, "utf-8")
    msg['From'] = settings.SMTP_SENDER
    msg['X-MC-Track'] = 'opens,clicks'
    msg['X-MC-Tags'] = mail_type
    msg['X-MC-Autotext'] = 'true'
    
    
    if post:
      mail_id = '%s-%s' % (post.id, db_name)
      mail_id = base64.b64encode(smaz.compress(mail_id)).replace('/', '-').rstrip('=')
      
      reply_to = 'post%s@%s' % (mail_id, settings.EMAIL_REPLY_TO_DOMAIN)
      msg['Reply-To'] = Header(reply_to, "utf-8")
      
    MAIL = SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
    
    if settings.SMTP_USE_TLS is True:
      MAIL.starttls()
    
    if settings.SMTP_PASSWORD:
      MAIL.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
    
    MAIL.sendmail(settings.SMTP_SENDER, 
                  to_addresses, msg.as_string()) 
    MAIL.quit()
    
    return True
  else:
    return False

#===============================================================================
# Snowflake IDs
#===============================================================================
SNOWFLAKE_REQUEST_URL = 'http://%s/' % settings.SNOWFLAKE_SERVER
def new_id():
  resp = requests.get(SNOWFLAKE_REQUEST_URL)
  return long(resp.text)

def is_snowflake_id(_id):
  if not _id:
    return False
  if isinstance(_id, UUID):
    return False
  if isinstance(_id, long):
    return True
  elif isinstance(_id, int):
    return True
  elif _id.isdigit() and len(str(_id)) > 13:
    return True
  return False

  

#===============================================================================
# Securely hash and check passwords using PBKDF2
#===============================================================================

# Parameters to PBKDF2. Only affect new passwords.
SALT_LENGTH = 12
KEY_LENGTH = 24
HASH_FUNCTION = 'sha256'  # Must be in hashlib.
# Linear to the hashing time. Adjust to be high but take a reasonable
# amount of time on your server. Measure with:
# python -m timeit -s 'import passwords as p' 'p.make_hash("something")'
COST_FACTOR = 10000

def make_hash(password):
    """Generate a random salt and return a new hash for the password."""
    if isinstance(password, unicode):
        password = password.encode('utf-8')
    salt = b64encode(urandom(SALT_LENGTH))
    return 'PBKDF2$%s$%s$%s$%s' % (HASH_FUNCTION,
                                   COST_FACTOR,
                                   salt,
                                   b64encode(pbkdf2_bin(password, 
                                                        salt, 
                                                        COST_FACTOR, 
                                                        KEY_LENGTH,
                                                        getattr(hashlib, 
                                                                HASH_FUNCTION)
                                                        )
                                             )
                                   )

def check_hash(password, hash_):
    """Check a password against an existing hash."""
    if isinstance(password, unicode):
        password = password.encode('utf-8')
    algorithm, hash_function, cost_factor, salt, hash_a = hash_.split('$')
    assert algorithm == 'PBKDF2'
    hash_a = b64decode(hash_a)
    hash_b = pbkdf2_bin(password, salt, int(cost_factor), len(hash_a),
                        getattr(hashlib, hash_function))
    assert len(hash_a) == len(hash_b)  # we requested this from pbkdf2_bin()
    # Same as "return hash_a == hash_b" but takes a constant time.
    # See http://carlos.bueno.org/2011/10/timing.html
    diff = 0
    for char_a, char_b in izip(hash_a, hash_b):
        diff |= ord(char_a) ^ ord(char_b)
    return diff == 0
  
#===============================================================================
# Long-polling
#===============================================================================
HOST = PORT = None
EVENTS = {}

  
def utctime():
  return float(datetime.utcnow().strftime('%s.%f'))


def friendly_format(ts, offset=0, short=False):
  try:
    ts = float(ts)
  except TypeError:
    return ts
  
  if offset:
    ts = ts + int(offset)
  
  if short:
    now = datetime.fromtimestamp(utctime() + int(offset))
    ts = datetime.fromtimestamp(int(ts))
    delta = datetime(now.year, now.month, now.day, 23, 59, 59) - ts
    
    if now.year - ts.year != 0:
      text = ts.strftime('%B %d, %Y')
    elif delta.days == 0:
      text = 'Today at %s' % ts.strftime('%I:%M%p')
    elif delta.days == 1:
      text = 'Yesterday at %s' % ts.strftime('%I:%M%p')
    elif delta.days in [2, 3]:
      text = ts.strftime('%A at %I:%M%p')
    else:
      text = '%s %s at %s' % (months[ts.month], ts.day, ts.strftime('%I:%M%p'))      
  else:
    ts = datetime.fromtimestamp(ts)
    text = ts.strftime('%A, %B %d, %Y at %I:%M%p')
  
  return text.replace(' 0', ' ').replace('AM', 'am').replace('PM', 'pm')


def get_interface_ip(ifname):
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  return socket.inet_ntoa(fcntl.ioctl(s.fileno(),
                                      0x8915,  # SIOCGIFADDR
                                      struct.pack('256s', ifname[:15]))[20:24])

def get_lan_ip():
  ip = socket.gethostbyname(socket.gethostname())
  if ip.startswith("127."):
    interfaces = ["eth0", "eth1", "eth2",
                  "wlan0", "wlan1", "wifi0",
                  "ath0", "ath1", "ppp0"]
    for ifname in interfaces:
      try:
        ip = get_interface_ip(ifname)
        break
      except IOError:
        pass
  return ip




#def get_tags(content):
#  tags = re.compile('#([A-Za-z0-9_]+)').findall(content)
#  return [tag.lower() for tag in tags]
  
def sizeof(num):
  try:
    num = float(num)
  except ValueError:
    return False
  for x in ['bytes','KB','MB','GB','TB']:
    if num < 1000:
      size = "%3.1f %s" % (num, x)
      return size.replace('.0', '')
    num /= 1024.0
    
def image_data_uri(filename):
  mimetype = mimetypes.guess_type(filename)[0]
  if os.path.exists(filename):
    content = open(filename).read()
  elif filename.startswith('http'):
    content = urlopen(filename).read()
  data = "data:%s;base64,%s" % (mimetype, 
                                base64.encodestring(content)\
                                .replace('\n', ''))
  return data
  
def datetime_string(timestamp):
  s = datetime.fromtimestamp(int(timestamp))\
              .strftime('%A, %B %d, %Y at %I:%M%p')
  s = s.replace(' 0', ' ')\
       .replace('AM', 'am')\
       .replace('PM', 'pm')
  return s

def isoformat(timestamp):
  return datetime.fromtimestamp(int(timestamp)).isoformat()

def get_words(text):
  word_regex = '[a-zA-Z0-9ạảãàáâậầấẩẫăắằặẳẵóòọõỏôộổỗồốơờớợởỡ' \
             + 'éèẻẹẽêếềệểễúùụủũưựữửừứíìịỉĩýỳỷỵỹđ]+'
  return re.compile(word_regex, re.I).findall(text.strip().lower())

def get_database_names():
  key = 'db_names'
  db_names = cache.get(key)
  if not db_names:
    db_names = DATABASE.database_names()
    db_names = list(db_names)
    cache.set(key, db_names)
  return db_names if isinstance(db_names, list) else []

def get_database_name():
  db_name = None
  if request:
    hostname = request.headers.get('Host')
    if hostname:
      db_name = hostname.split(':')[0].lower().strip().replace('.', '_')
  
  if not db_name:
    db_name = settings.PRIMARY_DOMAIN.replace('.', '_')
  
  db_names = get_database_names()
  if db_name not in db_names:
    # Ensure indexes
    DATABASE[db_name].owner.ensure_index('session_id', background=True)
    DATABASE[db_name].owner.ensure_index('email', background=True)
    DATABASE[db_name].owner.ensure_index('name', background=True)
    DATABASE[db_name].owner.ensure_index('password', background=True)
    DATABASE[db_name].owner.ensure_index('members', background=True)
    DATABASE[db_name].notification.ensure_index('receiver', background=True)
    DATABASE[db_name].notification.ensure_index('is_unread', background=True)
    DATABASE[db_name].notification.ensure_index('timestamp', background=True)
    
    DATABASE[db_name].stream.ensure_index('viewers', background=True)
    DATABASE[db_name].stream.ensure_index('last_updated', background=True)
    DATABASE[db_name].stream.ensure_index('when', background=True)
    DATABASE[db_name].status.ensure_index('archived_by', background=True)
    DATABASE[db_name].stream.ensure_index('is_removed', background=True)
    
    DATABASE[db_name].url.ensure_index('url', background=True)
#    DATABASE[db_name].hashtag.ensure_index('name', background=True)

  return db_name

def get_url_info(url, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  info = db.url.find_one({"url": url})
  if info:
    return URL(info)
  else:
    return URL({"url": url})


def get_url_description(url, bypass_cache=False, db_name=None):
  if not db_name:  
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  
  if '.' not in url and '/' not in url:
    return False
  
  
  info = dict()
  if not url.startswith('http'):
    url = 'http://' + url
    
  url_info = db.url.find_one({'url': url})   
  if (url_info and 
      not bypass_cache and 
      abs(utctime() - url_info.get('timestamp')) < 86400 * 90):  # only refresh if after 90 days
      return url_info
  
  
  mimetype = mimetypes.guess_type(url.rsplit('?', 1)[0])[0] 
  if mimetype and mimetype.startswith('image'):
    resp = requests.head(url, headers={'Accept-Encoding': ''})
    info['size'] = int(resp.headers.get('content-length', 0))
    info['content_type'] = resp.headers.get('content-type')    
    
  else:
    if ('stackoverflow.com' in url or
        'stackexchange.com' in url or 
        'superuser.com' in url or
        'serverfault.com' in url) and settings.HTTP_PROXY:
      html = requests.get(url, proxies={'http': settings.HTTP_PROXY}).content
      article = goose.extract(raw_html=html)
    else:
      try:
        article = goose.extract(url=url)
      except IOError: # stopwords for this language is not found
        return False
        
    info = {'title': article.title,
            'favicon': article.meta_favicon,
            'tags': list(article.tags),
            'description': article.meta_description,
            'text': article.cleaned_text}
    if article.top_image:
      info['img_src'] = article.top_image.get_src()
      info['img_bytes'] = article.top_image.bytes
      info['img_size'] = (article.top_image.width, article.top_image.height)
    
  info['timestamp'] = utctime()
  if not url_info:
    info['url'] = url
    info['_id'] = new_id()
    db.url.insert(info)     
  else:
    db.url.update({'url': url}, {'$set': info}) 
  return info


# User Actions -----------------------------------------------------------------
#def get_email(session_id, message_id):
#  user_id = get_user_id(session_id)
#  viewers = get_group_ids(user_id)
#  viewers.append(user_id)
#  
#  message = DATABASE.stream.find_one({'message_id': message_id,
#                                          'viewers': {'$in': viewers}})
#  if not message:
#    thread = DATABASE.stream.find_one({'viewers': {'$in': viewers}}
#                                           'comments.message_id': message_id})
#    if thread:
#      comments = thread['comments']
#      for comment in comments:
#        if comment.get('message_id') == message_id:
#          message = comment
#          message['subject'] = thread['subject']
#          message['body'] = comment['message']
#          break
#  return None

  

def get_friend_suggestions(user_info):
  user_id = user_info['_id']
  
  key = '%s:friends_suggestion' % user_id
  users = cache.get(key)
  if users is not None:
    return users
  
  facebook_friend_ids = user_info.get('facebook_friend_ids', [])
  google_contacts = user_info.get('google_contacts', [])
  
  contact_ids = user_info.get('contacts', [])
    
  user_ids = set()
  
  shuffle(facebook_friend_ids)
  shuffle(google_contacts)
  
  checklist = facebook_friend_ids[:5]
  checklist.extend(google_contacts[:5])
  
  for i in checklist:
    if '@' in i:
      uid = get_user_id(email=i)
    else:
      uid = get_user_id(facebook_id=i)
    
    if uid and uid not in contact_ids and uid != user_id:
      user_ids.add(uid)
  
  users = []
  for i in user_ids:
    user = get_user_info(i)
    if user.id not in contact_ids:
      users.append(user)
      if len(users) >= 5:
        break
      
  cache.set(key, users)
  
  return users


def get_user_id(session_id=None, facebook_id=None, email=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not session_id and not facebook_id and not email:
    return None
  
  key = '%s:%s:uid' \
      % (db_name, session_id if session_id \
                             else facebook_id if facebook_id else email)
  user_id = cache.get(key)
  if user_id:
    return user_id
  
  if email:
    user = db.owner.find_one({"email": email.lower().strip(),
                              "password": {"$ne": None}}, {'_id': True})
  elif facebook_id:
    user = db.owner.find_one({"facebook_id": facebook_id}, {'_id': True})
  else:  
    user = db.owner.find_one({"session_id": session_id}, {'_id': True})
    
  if user:
    user_id = user.get("_id")
    cache.set(key, user_id)
    return user_id
    
def get_session_id(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if user_id and user_id != 'public':
    user = db.owner.find_one({"_id": long(user_id)}, {'session_id': True,
                                                      'password': True})
    if not user:
      return False
    
    if user.has_key('session_id'):
      return user.get("session_id")
    
    elif not user.has_key('password'): # user chưa tồn tại, tạo tạm 1 session_id
      session_id = hashlib.md5('%s|%s' % (user_id, utctime())).hexdigest()
      db.owner.update({'_id': user['_id']}, 
                            {'$set': {'session_id': session_id}})
      return session_id

def is_exists(email=None, db_name=None):
  if db_name is not None:
    if db_name in get_database_names():
      return True
    return False
  elif db_name == settings.PRIMARY_DOMAIN.split(':')[0].replace('.', '_'):
    return True
  else:
    db_name = get_database_name()
    db = DATABASE[db_name]
    
    email = email.strip().lower()
    user = db.owner.find_one({"email": email, 
                              "password": {"$ne": None}}, 
                             {'_id': True})
    if user:
      return True
    return False

def is_ascii(s):
  return all(ord(c) < 128 for c in s)



def s3write(filename, filedata, overwrite=True, content_type=None):
  if not BUCKET:
    return False
  for __ in xrange(5):
    try:
      k = Key(BUCKET)
      k.name = filename
      
      # cache forever
      headers = {'Expires': '31 December 2037 23:59:59 GMT',
                 'Cache-Control': 'public, max-age=315360000'}
      
      # make avatar image (resized) public
      if re.compile('.*_\d+.jpg$').match(filename):
        headers['x-amz-acl'] = 'public-read'
        headers['Content-Type'] = 'image/jpeg'
      
      k.set_contents_from_string(filedata, headers=headers)
      return True
    except Exception:
      continue


def move_to_s3(fid, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  datastore = GridFS(db)
  t0 = utctime()
  if (isinstance(fid, str) or isinstance(fid, unicode)) and '|' in fid:
    filename, content_type, filedata = fid.split('|', 2)
    s3write(filename, filedata, True, content_type)
  else:
    if not isinstance(fid, ObjectId):
      fid = ObjectId(fid)
    f = datastore.get(fid)
    filename = f.filename
    s3write(filename, f.read(), overwrite=True, content_type=f.content_type)
    datastore.delete(fid)
  db['s3'].update({'name': filename}, {'$set': {'exists': True}})
  return True


def s3_url(filename, expires=5400, 
           content_type='application/octet-stream', disposition_filename=None):
  if not BUCKET:
    return False
  key = '%s:%s:%s:s3_url' % (filename, content_type, disposition_filename)
  url = cache.get(key)
  if not url:
    k = Key(BUCKET)
    k.name = filename
    headers = dict()
    headers['response-content-type'] = content_type \
                                if content_type else 'application/octet-stream'
    if disposition_filename:
      if is_ascii(disposition_filename):
        headers['response-content-disposition'] = 'attachment;filename="%s"' \
                                                % disposition_filename
      else:
        headers['response-content-disposition'] = 'attachment;filename="%s"' \
                                                % unidecode(unicode(disposition_filename))
#         msg = EmailMsg()
#         msg.add_header('Content-Disposition', 'attachment', 
#                        filename=('utf-8', '', disposition_filename))
#         headers['response-content-disposition'] = msg.values()[0].replace('"', '')
       
    url = k.generate_url(expires_in=expires, 
                         method='GET', response_headers=headers)
    
    # expire trước 30 phút để tránh trường hợp lấy phải url cache đã expires trên S3
    cache.set(key, url, expires - 1800)
  return url

def is_s3_file(filename, db_name=None):
  if not BUCKET:
    return False
  
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  key = 'is_s3_file:%s' % filename
  status = cache.get(key)
  
  if status is not None:
    return status
  
  # check in db
  info = db.s3.find_one({'name': filename})
  if info:
    return info.get('exists')

  # check via boto
  k = Key(BUCKET)
  k.name = filename
  if k.exists():
    cache.set(key, 1)
  
    # persitant cache
    db.s3.insert({'name': filename, 'exists': True})
    
    return True
  else:
    cache.set(key, 0)
    
    # persitant cache
    db.s3.insert({'name': filename, 'exists': False})
  
    return False

def get_username(user_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  key = '%s:name' % user_id
  name = cache.get(key)
  if name:
    return name
  
  user = db.owner.find_one({"_id": long(user_id)}, {'name': True})
  if user:
    cache.set(key, user.get('name'))
    return user.get("name")
  return None

def get_user_id_from_username(username):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user = db.owner.find_one({"name": username}, {'_id': True})
  if user:
    user_id = user.get("_id")
    return user_id
  return None
  

def notify_me(email):
  email = email.strip().lower()
  db.waiting_list.update({"email": email}, 
                               {"$set": {'timestamp': utctime()}},
                               upsert=True)
  send_mail_queue.enqueue(send_mail, email, mail_type='thanks', db_name=db_name)
  return True
  




def update_session_id(email, session_id, db_name):
  email = email.strip().lower()
  DATABASE[db_name].owner.update({'email': email},
                        {'$set': {'session_id': session_id}})
  return True
  
def sign_in(email, password, user_agent=None, remote_addr=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not email:
    return False
  if not password:
    return False
  email = email.strip().lower()
  user = db.owner.find_one({"email": email}, {'password': True,
                                              'salt': True,
                                              'session_id': True})
  if not user or not user.get('password'):
    return None
  else:
    session_id = None
    if user.get('password') is True:
      return False
    elif '$' in user.get('password'): # PBKDF2 hashing
      ok = check_hash(password, user['password'])
    else:  # old password hashing (sha512 + salt)
      salt = user["salt"]
      password = hashlib.sha512(password + salt).hexdigest()
      ok = True if password == user["password"] else False
      
    if ok:
      query = {"$push": {'history': {"user_agent": user_agent,
                                     "remote_addr": remote_addr,
                                     "timestamp": utctime(),
                                     "status": "success"}}}
      if user.has_key('session_id'):
        session_id = user['session_id']
      else:
        session_id = hashlib.md5(email + str(utctime())).hexdigest()
        query['$set'] = {'session_id': session_id}
      
      db.owner.update({"email": email}, query)
    else:
      if user_agent:
        db.owner.update({"email": email},
                        {"$push": 
                         {"history": 
                          {"user_agent": user_agent,
                           "remote_addr": remote_addr,
                           "timestamp": utctime(),
                           "status": "fail"}}})
      return False 

  return session_id


def invite(session_id, email, group_id=None, msg=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  user = get_user_info(user_id)
  email = email.strip().lower()
  code = hashlib.md5(email + str(utctime())).hexdigest()
  info = db.owner.find_one({'email': email}, {'password': True})
  is_new_user = True
  if info:
    if info.has_key('password'):  # existed account
      _id = info['_id']
      is_new_user = False
    else:
      _id = info['_id']
      db.owner.update({'_id': _id},
                      {'$set': {'ref': user_id,
                                'session_id': code,
                                'timestamp': utctime()}})
  else:
    _id = new_id()
    db.owner.insert({'_id': _id,
                     'email': email,
                     'ref': user_id,
                     'timestamp': utctime(),
                     'session_id': code})
    
  if str(group_id).isdigit():
    db.owner.update({'_id': long(group_id), 'members': user_id}, 
                    {'$addToSet': {'members': _id}})
    group = get_group_info(session_id, group_id)
  else:
    group = Group({})
    

  send_mail_queue.enqueue(send_mail, email, 
                          mail_type='invite', 
                          code=code, 
                          is_new_user=is_new_user,
                          user_id=user.id,
                          username=user.name, 
                          msg=msg,
                          group_id=group.id, 
                          group_name=group.name,
                          db_name=db_name)
  
  db.owner.update({'_id': user_id}, {'$addToSet': {'google_contacts': email}})
    
  return True
  
def complete_profile(code, name, password, gender, avatar):  
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = {}
  info["name"] = name
  info["password"] = make_hash(password)
  info["verified"] = 1
  info["gender"] = gender
  info['avatar'] = avatar
  info['session_id'] = hashlib.md5(code + str(utctime())).hexdigest()
  db.owner.update({'session_id': code}, {'$set': info})
  user_id = get_user_id(code)
  cache.delete(code)
  cache.delete('%s:info' % user_id)
  
  # Send notification to friends
  user = get_user_info(user_id)
  
  session_id = info['session_id']
  friends = db.owner.find({'google_contacts': user.email})
  for user in friends:
    notification_queue.enqueue(new_notification, 
                               session_id, user['_id'], 
                               'friend_just_joined', 
                               None, None, db_name=db_name)
  
  return session_id

def sign_in_with_google(email, name, gender, avatar, 
                        link, locale, verified=True, 
                        google_contacts=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  
  if not email:
    return False
  
  email = email.lower().strip()
  
  if not google_contacts:
    google_contacts = []
  
  notify_list = []
  user = db.owner.find_one({'email': email})
  if user:
    if user.get('google_contacts'):
      notify_list = [i for i in google_contacts \
                     if i not in user.get('google_contacts') and i != email]
    else:
      notify_list = [i for i in google_contacts if i != email]
    
    
    session_id = user.get('session_id')
    if not session_id:
      session_id = hashlib.md5(email + str(utctime())).hexdigest()
      info = {'session_id': session_id}
      if not user.get('password'):
        info['password'] = True
      if notify_list:
        info['google_contacts'] = google_contacts
      db.owner.update({'_id': user.get('_id')}, {'$set': info})
    else:
      if notify_list:
        db.owner.update({'_id': user.get('_id')}, 
                        {'$set': {'google_contacts': google_contacts}})
        
  else:
    session_id = hashlib.md5(email + str(utctime())).hexdigest()
    info = {}
    info["_id"] = new_id()
    info["email"] = email
    info["name"] = name
    info["avatar"] = avatar
    info["password"] = True
    info['session_id'] = session_id
    info["verified"] = verified
    info["timestamp"] = utctime()
    info['gender'] = gender
    info['link'] = link
    info['locale'] = locale
    if google_contacts:
      info['google_contacts'] = google_contacts
      notify_list = [i for i in google_contacts if i != email]
    
    db.owner.insert(info)
    
    cache.delete('%s:all_users' % db_name)
    
    for user_id in get_network_admin_ids(db_name):
      notification_queue.enqueue(new_notification, 
                                 session_id, user_id, 
                                 'new_user', 
                                 None, None, db_name=db_name)
    

  if notify_list:
    for email in notify_list:
      user = db.owner.find_one({'email': email.lower(), 
                                'password': {'$ne': None}}, {'_id': True})
      if user:
        user_id = user['_id']
        notification_queue.enqueue(new_notification, 
                                   session_id, 
                                   user_id, 
                                   'google_friend_just_joined', 
                                   None, None, 
                                   db_name=db_name)
  

  return session_id

def sign_in_with_facebook(email, name=None, gender=None, avatar=None, 
                          link=None, locale=None, timezone=None, 
                          verified=None, facebook_id=None, 
                          facebook_friend_ids=None, db_name=None):
  if not email:
    return False

  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  email = email.lower().strip()
  
  facebook_friend_ids = list(set(facebook_friend_ids))
  
  notify_list = []
  user = db.owner.find_one({'email': email})
  if user:
    if user.get('facebook_friend_ids'):
      notify_list = [i for i in facebook_friend_ids \
                     if i not in user.get('facebook_friend_ids')]
    else:
      notify_list = facebook_friend_ids
    
    session_id = user.get('session_id')
    if not session_id:
      session_id = hashlib.md5(email + str(utctime())).hexdigest()
      info = {'session_id': session_id}
      if not user.get('password'):
        info['password'] = True
      if not user.get('facebook_id'):
        info['facebook_id'] = facebook_id
      if notify_list:
        info['facebook_friend_ids'] = facebook_friend_ids
      
      db.owner.update({'_id': user.get('_id')}, {'$set': info})      
    else:
      if notify_list:
        db.owner.update({'_id': user.get('_id')}, 
                        {'$set': {'facebook_friend_ids': facebook_friend_ids}})    
      
    info = user
      
  else:
    session_id = hashlib.md5(email + str(utctime())).hexdigest()
    info = {}
    info["_id"] = new_id()
    info["email"] = email
    info["name"] = name
    info["avatar"] = avatar
    info["password"] = True
    info['session_id'] = session_id
    info["verified"] = verified
    info["timestamp"] = utctime()
    info['gender'] = gender
    info['link'] = link
    info['locale'] = locale
    info['timezone'] = timezone
    info['facebook_id'] = facebook_id
    if facebook_friend_ids:
      info['facebook_friend_ids'] = facebook_friend_ids
      notify_list = facebook_friend_ids
      
    db.owner.insert(info)
    
    cache.delete('%s:all_users' % db_name)
  
    for user_id in get_network_admin_ids(db_name):
      notification_queue.enqueue(new_notification, 
                                 session_id, user_id, 
                                 'new_user', 
                                 None, None, db_name=db_name)
      
  if notify_list:
    for i in notify_list:
      user_id = get_user_id(facebook_id=i)
      if user_id and user_id != info['_id']:
        notification_queue.enqueue(new_notification, 
                                   session_id, user_id, 
                                   'facebook_friend_just_joined', 
                                   None, None, db_name=db_name)
  
  return session_id
  
def sign_in_with_twitter():
  pass
  

def sign_up(email, password, name, user_agent=None, remote_addr=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  email = email.strip().lower()
  name = name.strip()
  raw_password = password
  
  # Validation
  if validate_email(email) is False:
    return False
  if len(password) < 6:
    return False
  
  user = db.owner.find_one({'email': email})
  if user and user.get('password'):
    return False
  
  info = {}
  password = make_hash(raw_password)
  token = hashlib.md5(email + str(utctime())).hexdigest()
  if not user:
    info["email"] = email
    info["name"] = name
    info["password"] = password
    info["verified"] = 0
    info["token"] = token
    info["timestamp"] = utctime()
    info["_id"] = new_id()
  
    db.owner.insert(info)
  else:
    info['name'] = name
    info["password"] = password
    info["verified"] = 0
    info["token"] = token
    info["timestamp"] = utctime()
    
    db.owner.update({'email': email}, {'$set': info})
    
    info['_id'] = user['_id']
    
  cache.delete('%s:all_users' % db_name)
  
  session_id = sign_in(email, raw_password, user_agent, remote_addr)
  
  for user_id in get_network_admin_ids(db_name):
    notification_queue.enqueue(new_notification, 
                               session_id, user_id, 
                               'new_user', 
                               None, None, db_name=db_name)
    
    
  # notify friends
  friends = db.owner.find({'google_contacts': email})
  for user in friends:
    user_id = user['_id']
    notification_queue.enqueue(new_notification, 
                               session_id, 
                               user_id, 
                               'google_friend_just_joined', 
                               None, None, 
                               db_name=db_name)
    
  
  
#  subject = 'E-mail verification for the 5works Public Beta'
#  body = render_template('email/verification.html', 
#                         name=name, domain='jupo.comm', token=token)
#  send_mail(email, subject, body)
  
  # init some data
#   new_reminder(session_id, 'Find some contacts')
#   new_reminder(session_id, 'Upload a profile picture (hover your name at the top right corner, click "Change Profile Picture" in drop down menu)')
#   new_reminder(session_id, 'Hover over me and click anywhere on this line to check me off as done')

  # add user to "Welcome to 5works" group
#  db.owner.update({'_id': 340916998231818241}, 
#                        {'$addToSet':{'members': info['_id']}})

  return session_id

def sign_out(session_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  cache.delete(session_id)
  # remove last session_id
  
  cache.delete('%s:uid' % session_id)
  
  db.owner.update({"session_id": session_id}, 
                  {"$unset": {"session_id": 1}})
  return True

def change_password(session_id, old_password, new_password):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  user = db.owner.find_one({'_id': long(user_id)}, {'password': True,
                                                          'salt': True})
  if user and user.get('password'):
    if '$' in user['password']: # PBKDF2 hashing
      ok = check_hash(old_password, user['password'])
    else:  # old password hashing (sha512 + salt)
      salt = user["salt"]
      password = hashlib.sha512(old_password + salt).hexdigest()
      ok = True if password == user["password"] else False
    
    if ok:
      db.owner.update({'_id': user_id}, 
                      {'$set': {'password': make_hash(new_password)}}, 
                      safe=True)
      cache.delete('%s:info' % user_id)
      return True
    
def reset_password(user_id, new_password):
  """ Be careful """
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  db.owner.update({'_id': long(user_id)}, 
                  {'$set': {'password': make_hash(new_password)},
                   '$unset': {'session_id': 1}}, 
                  safe=True)
  
  cache.delete('%s:info' % user_id)
  return True
    

def verify(token):
  pass

def new_verify_token(email):
  pass

def forgot_password(email):
  db_name = get_database_name()
  
  user = DATABASE[db_name].owner.find_one({'email': email.strip().lower()})
  if user:
    temp_password = uuid4().hex
    FORGOT_PASSWORD.set(temp_password, email)
    FORGOT_PASSWORD.expire(temp_password, 3600)
    send_mail_queue.enqueue(send_mail, email, mail_type='forgot_password', 
                            temp_password=temp_password, db_name=db_name)
    return True
  else:
    return False
  
    
    
def update_pingpong_timestamp(session_id):
  user_id = get_user_id(session_id)
  PINGPONG.set(user_id, utctime())
  return True

def get_pingpong_timestamp(user_id):
  ts = PINGPONG.get(user_id)
  if ts:
    return float(ts)

def set_status(session_id, status):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id, db_name=db_name)
  if not user_id:
    return False
  
  if '|' in status:
    chat_id, _status = status.split('|')
    user = get_user_info(user_id, db_name=db_name)
    if _status:
      text = user.name + ' ' + _status
    else:
      text = ''
    
    if chat_id.startswith('user-'):
      uid = int(chat_id.split('-')[1])
      push_queue.enqueue(publish, int(uid), 'typing-status', 
                         {'chat_id': 'user-%s' % user_id, 'text': text}, db_name=db_name)
    else:
      topic_id = int(chat_id.split('-')[1])
      topic = get_topic_info(topic_id, db_name=db_name)
      user_ids = topic.member_ids
    
      for uid in user_ids:
        if uid != user_id:
          push_queue.enqueue(publish, int(uid), 'typing-status', 
                             {'chat_id': chat_id, 'text': text}, db_name=db_name)
    status = 'online'
  else:
    key = 'status:%s' % user_id
    cache.set(key, status)
    db.status.update({'user_id': user_id},
                     {'$set': {'status': status,
                               'timestamp': utctime()}}, upsert=True)
    push_queue.enqueue(publish, user_id, 
                       'friends-online', status, 
                       db_name=db_name)
  
  key = '%s:status' % user_id
  cache.set(key, status, 86400)
  
  key = '%s:last_online' % user_id
  cache.delete(key)
  return True

def check_status(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if user_id is None:
    return 'offline'
  
  user_id = long(user_id)
  key = '%s:status' % user_id
  status = cache.get(key)
  if not status:
    user = db.status.find_one({'user_id': user_id}, 
                              {'status': True})
    if not user:
      status = 'offline'
    else:
      status = user.get('status', 'offline')
      if status != 'offline':
        pingpong_ts = get_pingpong_timestamp(user_id)
        if pingpong_ts and utctime() - pingpong_ts > 150:  # lost ping pong signal > 150 secs -> offline
          status = 'offline'
    cache.set(key, status, 86400)

  if status == 'online' and (utctime() - last_online(user_id) > 5 * 60):  # quá 5 phút mà vẫn thấy online thì chắc là lỗi rồi 
    status = 'offline'
  return status

def is_online(user_id):
  if check_status(user_id) == 'online':
    return True
  
def last_online(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not is_snowflake_id(user_id):
    return 0
  
  key = '%s:last_online' % user_id
  ts = cache.get(key)
  if not ts:
    user = db.status.find_one({'user_id': long(user_id)}, 
                              {'timestamp': True})
    if user:
      ts = user.get('timestamp')
      cache.set(key, ts, 86400)
    else:
      ts = 0
  return ts
  

def get_online_coworkers(session_id):
  groups = get_groups(session_id)
  if not groups:
    return []
  coworkers = []
  for group in groups:
    for member in group.members:
      coworkers.append(member)
  online = []
  _ids = []
  owner_id = get_user_id(session_id)
  for user in set(coworkers):
    if not user.id:
      continue
    if str(user.id) == str(owner_id):
      continue
    status = check_status(user.id)
    if status in ['online', 'away']:
      if user.id not in _ids:
        user.status = status
        online.append(user)
        _ids.append(user.id)
  online = sorted(online, key=lambda k: k.name)
  return online

def get_all_users(limit=1000):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  key = '%s:all_users' % db_name
  users = cache.get(key)
  if users is None:  
    users = db.owner.find({'password': {'$ne': None}})\
                    .sort('timestamp', -1)\
                    .limit(limit)
    users = list(users)
    for user in users:
      if user.has_key('history'):
        user.pop('history')
      if user.has_key('facebook_friend_ids'):
        user.pop('facebook_friend_ids')
      if user.has_key('google_contacts'):
        user.pop('google_contacts')
      user['password'] = True
    cache.set(key, users)
  return [User(i, db_name=db_name) for i in users]

def get_all_groups(limit=300):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  groups = db.owner.find({'members': {'$ne': None}}).limit(limit)
  return [Group(i, db_name=db_name) for i in groups]
  
@line_profile
def get_coworkers(session_id, limit=100):
  if str(session_id).isdigit():
    user_id = long(session_id)
  else:
    user_id = get_user_id(session_id)

  key = '%s:coworkers' % user_id
  coworkers = cache.get(key)
  if coworkers:
    return coworkers[:limit]
  
  groups = get_groups(session_id)
  if not groups:
    return []
  coworkers = []
  _ids = set()
  for group in groups:
    for member in group.members:
      if member.id not in _ids:
        coworkers.append(member)
        _ids.add(member.id)
        
  coworkers = list(coworkers)
  cache.set(key, coworkers, 86400)
  
  coworkers = sorted(coworkers[:limit], 
                     key=lambda user: last_online(user.id), reverse=True)
  return coworkers

def get_friends(session_id):
  """
  coworkers, contacts, followers, following users
  """
  coworkers = get_coworkers(session_id)
  user_id = get_user_id(session_id)
  user_info = get_user_info(user_id)
  coworkers.extend(user_info.contacts)
  
  following_users = [get_user_info(i) for i in user_info.following_users]
  followers = [get_user_info(i) for i in user_info.followers]
  
  coworkers.extend(following_users)
  coworkers.extend(followers)
  
  return coworkers


def get_contacts(session_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return []
  
  info = db.owner.find_one({'_id': user_id}, {'contacts': True})
  if not info:
    return []
  
  contact_ids = info.get('contacts', [])
  return [get_user_info(i) for i in contact_ids]


def get_coworker_ids(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  groups = db.owner.find({"members": user_id}, {'members': True})
  user_ids = set()
  for group in groups:
    for user_id in group.get('members'):
      user_ids.add(user_id)
  return user_ids
  

def is_group(_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not is_snowflake_id(_id):
    return None
  
  key = '%s:is_group' % _id
  if cache.get(key) == 1:
    return True
  
  if not _id:
    return False
  
  if _id == 'public':
    return True
  
  info = db.owner.find_one({'_id': long(_id)}, {'members': True})
  if info and info.has_key('members'):
    cache.set(key, 1)
    return True
  
  cache.set(key, 0)
  return False

def update_user_info(session_id, info):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  db.owner.update({'_id': user_id}, {'$set': info})
  
  cache.delete('%s:info' % user_id)
  
#  if info.has_key('name') or info.has_key('avatar'):
#    clear_html_cache(post_id)
  return True

def update_utcoffset(session_id, offset):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if str(session_id).isdigit():
    user_id = long(session_id)
  else:
    user_id = get_user_id(session_id)
    
  if cache.get('utcoffset', namespace=user_id) != offset:
    db.owner.update({'_id': user_id}, 
                    {'$set': {'utcoffset': offset}})
    
    key = '%s:info' % user_id
    cache.delete(key)
    
    cache.set('utcoffset', offset, namespace=user_id)
  return True

def get_utcoffset(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not str(user_id).isdigit():
    return 0  
  
  offset = cache.get('utcoffset', namespace=user_id)
  if not offset:
    info = db.owner.find_one({'_id': long(user_id)}, {'utcoffset': True})
    if info:
      offset = info.get('utcoffset', 0)
    else:
      return 0
  return offset

def get_user_info(user_id=None, facebook_id=None, email=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if user_id and not is_snowflake_id(user_id):
    return User({})
    
  if email and '@' not in email:
    return User({})
    
  if not user_id and not facebook_id and not email:
    return User({})
  
  if not user_id:
    user_id = get_user_id(facebook_id=facebook_id, email=email, db_name=db_name)
  
  key = '%s:info' % (user_id if user_id else facebook_id if facebook_id else email)
  info = cache.get(key)
  if not info:  
    if facebook_id:
      info = db.owner.find_one({'facebook_id': facebook_id, 
                                'password': {'$ne': None}})
    elif email:
      info = db.owner.find_one({'email': email.strip().lower(), 
                                'password': {'$ne': None}})
    elif '@' in str(user_id):
      info = db.owner.find_one({'email': user_id})
    elif str(user_id).isdigit():
      info = db.owner.find_one({"_id": long(user_id)})
    else:
      info = None
      
    if info:
      if info.has_key('history'):
        info.pop('history')
    
      cache.set(key, info)

  return User(info, db_name=db_name) if info else User({})


def get_owner_info(session_id=None, uuid=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not session_id and not uuid:
    return User({})
  
  elif session_id:
    user_id = get_user_id(session_id, db_name=db_name)
    key = '%s:info' % user_id
    info = cache.get(key)
    if not info:
      info = db.owner.find_one({"_id": user_id})
      if info:
        cache.set(key, info)
  
  elif uuid == 'public': 
    info = {'_id': 'public',
            'name': 'Public',
            'members': [] # get_followers(session_id)
            }
  else:
    if '@' in str(uuid):
      info = db.owner.find_one({'email': uuid})
    else:
      info = db.owner.find_one({"_id": long(uuid)})
  if info and info.has_key('members'):
    return Group(info, db_name=db_name)
  return User(info, db_name=db_name)

def get_owner_info_from_uuid(uuid, db_name=None):
  if not db_name: 
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not uuid:
    return User({})
  key = '%s:info' % uuid
  info = cache.get(key)
  if not info: 
    if uuid == 'public': 
      info = {'_id': 'public',
              'name': 'Public',
              'members': [] # get_followers(session_id)
              }
    else:
      if '@' in str(uuid):
        info = db.owner.find_one({'email': uuid})
      else:
        info = db.owner.find_one({"_id": long(uuid)})  
    cache.set(key, info)
  if info and info.has_key('members'):
    return Group(info, db_name=db_name)
  return User(info, db_name=db_name)

def autocomplete(session_id, query):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return []
  
  if query.startswith('#'):
    hashtags = db.hashtag.find({'name': re.compile('^' + query, 
                                                   re.IGNORECASE)}).limit(5)
    items = [{'name': i.get('name'), 
              'id': str(i.get('_id'))} for i in hashtags]
  else:
    contacts = get_user_info(user_id).contacts
    groups = get_groups(session_id)
    
    owners = contacts
    owners.extend(groups)
    
    query = query.strip().lower()
    items = []
    for i in owners:
      if i.name and \
         query in unidecode(unicode(i.name.lower())) or \
         query in i.name.lower():
        info = {'name': i.name, 
                'id': i.id, 
                'type': 'group' if i.is_group() else 'user'}
        items.append(info)
    
  if not items:
    users = db.owner.find({'email': re.compile('^%s.*' % query, 
                                               re.IGNORECASE)}, 
                          {'name': True, 'email': True})\
                    .limit(5)
    items = [{'name': i.get('email'),
              'id': str(i.get('_id'))} \
             for i in users if i.get('_id') != user_id]
  return items

# Notifications ----------------------------------------------------------------

def is_removed(feed_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if db.stream.find_one({'_id': long(feed_id), 'is_removed': True}):
    return False
  return True

def new_notification(session_id, receiver, type, 
                     ref_id=None, ref_collection=None, comment_id=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = {'_id': new_id(),
          'receiver': receiver,
          'ref_id': ref_id,
          'ref_collection': ref_collection,
          'comment_id': comment_id,
          'type': type,
          'is_unread': True,
          'timestamp': utctime()}
  
  if session_id:
    sender = get_user_id(session_id, db_name=db_name)
    if sender:
      info['sender'] = sender
  
  notification_id = db.notification.insert(info)
  
  key = '%s:networks' % get_email_addresses(receiver)
  cache.delete(key)
  
  cache.delete('notifications', receiver)
  cache.delete('unread_notifications', receiver)
  cache.delete('unread_notifications_count', receiver)
  
  unread_notifications_count = get_unread_notifications_count(receiver, 
                                                              db_name=db_name)
  push_queue.enqueue(publish, receiver, 'unread-notifications', 
                     unread_notifications_count, db_name=db_name)
  
  return notification_id

def get_unread_notifications(session_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if isinstance(session_id, int) or isinstance(session_id, long):
    user_id = session_id
  else:
    user_id = get_user_id(session_id, db_name=db_name)

  key = 'unread_notifications'
  out = cache.get(key, namespace=user_id)
  if out is not None:
    return out

  notifications = db.notification.find({'receiver': user_id,
                                        'is_unread': True})\
                                 .sort('timestamp', -1)

  offset = get_utcoffset(user_id)
  notifications = [Notification(i, offset, db_name) for i in notifications]
      
  results = odict()
  for i in notifications:
    if i.type in ['new_post', 'comment', 'mention', 
                  'message', 'like', 'update'] and not i.details:
      continue
    
    if not i.type:
      continue
    
    if i.type == 'like':
      id = '%s:%s' % (i.type, i.comment_id if i.comment_id else i.ref_id)
    elif i.type == 'new_user' or i.ref_collection == 'owner':
      id = '%s:%s:%s' % (i.type, i.sender.id, i.ref_id)
    else:
      id = '%s:%s' % (i.type, i.ref_id)
    
    if not results.has_key(i.date):
      results[i.date] = odict()
      
    
    if not results[i.date].has_key(id):
      results[i.date][id] = [i]
      user_ids = [i.sender.id]
    else:
      # duplicate prevention 
      if i.sender.id not in user_ids:
        results[i.date][id].append(i)
        user_ids.append(i.sender.id)
        
    
  cache.set(key, results, namespace=user_id)
  return results
  
def get_notifications(session_id, limit=25):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  
  key = 'notifications'
  out = cache.get(key, namespace=user_id)
  if out is not None:
    return out
  
  
  notifications = db.notification.find({'receiver': user_id})\
                                 .sort('timestamp', -1)\
                                 .limit(limit)

  offset = get_utcoffset(user_id)
  notifications = [Notification(i, offset, db_name) for i in notifications]
  results = odict()
  
  user_ids = {}
  for i in notifications:
    if i.type in ['new_post', 'comment', 'mention', 
                  'message', 'like', 'update'] and not i.details:
      continue
    
    if not i.type:
      continue
    
    if i.type == 'like':
      id = '%s:%s' % (i.type, i.comment_id if i.comment_id else i.ref_id)
    elif i.type == 'new_user' or i.ref_collection == 'owner':
      id = '%s:%s:%s' % (i.type, i.sender.id, i.ref_id)
    else:
      id = '%s:%s' % (i.type, i.ref_id)
    
    if not results.has_key(i.date):
      results[i.date] = odict()
      
    
    if not results[i.date].has_key(id):
      results[i.date][id] = [i]
      user_ids[id] = [i.sender.id]
    else:
      # prevent duplicate
      if i.sender.id not in user_ids[id]:
        results[i.date][id].append(i)
        user_ids[id].append(i.sender.id)
        
  cache.set(key, results, namespace=user_id)
  return results

  
def get_unread_notifications_count(session_id, db_name=None):
  if isinstance(session_id, int) or isinstance(session_id, long):
    user_id = session_id
  else:
    user_id = get_user_id(session_id, db_name=db_name)
  key = 'unread_notifications_count'
  out = cache.get(key, namespace=user_id)
  if out is not None:
    return out
    
  unread_notifications = get_unread_notifications(session_id, db_name)
  count = 0
  for k in unread_notifications.keys():
    for id in unread_notifications[k].keys():
      for n in unread_notifications[k][id]:
        count += 1
  
  cache.set(key, count, namespace=user_id)
  return count
  
    
def get_record(_id, collection='stream', db_name=None):
  if not collection \
  or isinstance(collection, int) \
  or isinstance(collection, long):
    collection = 'stream'
  
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if str(_id).isdigit():
    return db[collection].find_one({'_id': long(_id)})

def mark_all_notifications_as_read(session_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  
  cache.delete('notifications', user_id)
  cache.delete('unread_notifications', user_id)
  cache.delete('unread_notifications_count', user_id)
  
  db.notification.update({'receiver': user_id}, 
                         {'$unset': {'is_unread': 1}}, multi=True)
  
  return True

def mark_notification_as_read(session_id, notification_id=None, 
                              ref_id=None, type=None, ts=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not ts:
    ts = utctime()
    
  user_id = get_user_id(session_id)
  if notification_id:
    db.notification.update({'receiver': user_id, 
                            '_id': long(notification_id)},
                           {'$unset': {'is_unread': 1}})
  elif ref_id:
    db.notification.update({'receiver': user_id, 
                            'ref_id': long(ref_id)},
                           {'$unset': {'is_unread': 1}}, multi=True)
  else:
    db.notification.update({'receiver': user_id, 
                            'type': type,
                            'timestamp': {'$lt': float(ts)}},
                           {'$unset': {'is_unread': 1}}, multi=True)
    
  cache.delete('notifications', user_id)
  cache.delete('unread_notifications', user_id)
  cache.delete('unread_notifications_count', user_id)
  
  return True

# Feed/Stream/Focus Actions ----------------------------------------------------
def mark_as_read(session_id, post_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  post = get_feed(session_id, post_id)
  if not post.id:
    return False
  
  user_id = get_user_id(session_id)
  if (post.last_action.owner.id != user_id and 
      user_id not in post.read_receipt_ids):   # 1 user mở nhiều hơn 1 tab có thể dẫn đến gửi lặp nhiều lần
    
    ts = utctime()
    record = db.stream.find_and_modify({'_id': long(post_id)},
                                             {'$push': 
                                              {'read_receipts': 
                                               {'user_id': user_id,
                                                'timestamp': ts}
                                               }
                                              })
    if not record:
      return False
    
    if not record.has_key('read_receipts'):
      record['read_receipts'] = []
    
    record['read_receipts'].append({'user_id': user_id, 'timestamp': ts})
  
    viewers = record.get('viewers', [])
    user_ids = set()
    for i in viewers:
      if i == 'public':
        continue
      if is_group(i):
        member_ids = get_group_member_ids(i)
        for id in member_ids:
          user_ids.add(long(id))
      else:
        user_ids.add(long(i))
        
    for _id in user_ids:
      cache.clear(_id)
      push_queue.enqueue(publish, _id, 'read-receipts', record, db_name=db_name)
    
    # update notification
    mark_notification_as_read(session_id, ref_id=post_id)
    
    unread_notifications_count = get_unread_notifications_count(user_id,
                                                                db_name=db_name)
    push_queue.enqueue(publish, user_id, 'unread-notifications', 
                       unread_notifications_count, db_name=db_name)
    
    
    clear_html_cache(post_id)
    
    return True
  return False

def star(session_id, feed_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  db.stream.update({"_id": long(feed_id)}, 
                         {'$addToSet': {'starred': user_id}})
  receiver = get_record(feed_id)['owner']
  if user_id != receiver:
    new_notification(session_id, receiver, type='star', ref_id=feed_id)
  
  clear_html_cache(feed_id)  
  
  return feed_id

def unstar(session_id, feed_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  db.stream.update({"_id": long(feed_id)}, 
                         {'$pull': {'starred': user_id}})
  clear_html_cache(feed_id)  
  return feed_id

def pin(session_id, feed_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  db.stream.update({"_id": long(feed_id)}, 
                         {'$addToSet': {'pinned': user_id}})
  clear_html_cache(feed_id)  
  return feed_id

def unpin(session_id, feed_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  db.stream.update({"_id": long(feed_id)}, 
                         {'$pull': {'pinned': user_id}})
  clear_html_cache(feed_id)  
  return feed_id

def update_hashtag(tags):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not isinstance(tags, list):
    tags = [tags]
  for tag in tags:
    db.hashtag.update({'_id': tag.get('id')},
                            {'$set': {'name': tag.get('name'),
                                      'last_updated': utctime()},
                             '$inc': {'count': 1}}, upsert=True)
  return True
  

def get_hashtags(raw_text):
  hashtags = re.compile('(#\[.*?\))').findall(raw_text)
  hashtag_list = []
  if hashtags:
    for hashtag in hashtags:
      tag = re.compile('#\[(?P<name>.+)\]\((?P<id>.*)\)').match(hashtag)
      if not tag:
        continue
      else:
        tag = tag.groupdict()
      tag['id'] = tag['id'].split(':', 1)[-1]
      hashtag_list.append(tag)
  return hashtag_list

def get_mentions(raw_text):
  users = re.compile('(@\[.*?]\(.*?\))').findall(raw_text)
  user_list = []
  if users:
    for user in users:
      tag = re.compile('@\[(?P<name>.+)\]\((?P<id>.*?)\)')\
              .match(user)\
              .groupdict()
      tag['type'], tag['id'] = tag['id'].split(':', 1)
      if tag['id'].isdigit():
        tag['id'] = long(tag['id'])
      user_list.append(tag)
  return user_list

def unfollow_post(session_id, feed_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  db.owner.update({'_id': user_id}, 
                  {'$addToSet': {'unfollow_posts': long(feed_id)}})
  return feed_id

def new_email(owner_id, email, password):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  email = email.lower().strip()
  if db.email.find_one({'email': email}):
    return False
      
  db.email.insert({'email': email,
                   'password': password,
                   'owner': long(owner_id),
                   'last_uid': 0,
                   'timestamp': utctime(),
                   'last_updated': utctime()})
  return True

def reset_mail_fetcher():
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  db.email.update({}, {'$set': {'last_uid': 0}}, multi=True)
  db.stream.remove({'message_id': {'$ne': None}})
  db.owner.remove({'password': None, 
                   'privacy': None})

  return True

def get_email_addresses(session_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if (isinstance(session_id, int) or 
      isinstance(session_id, long) or 
      session_id.isdigit()):
    user_id = int(session_id)
  else:
    user_id = get_user_id(session_id)
  
  user_ids = [i['_id'] \
              for i in db.owner.find({'owner': user_id}, {'_id': True})]
  user_ids.append(user_id) 
  query = [{'owner': i} for i in user_ids]
  records = db.email.find({'$or': query})
  return [i['email'].strip() for i in records]

def get_user_id_from_email_address(email, db_name=None):
  if not email:
    return False
  
  if email and ('@' not in email or '.' not in email):
    return False
  
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  email = email.lower().strip()
  
  record = db.owner.find_one({'email': email.split('<')[-1].rstrip('>').strip()})
  if record:
    if record.has_key('owner'):
      uid = record['owner']
    else:
      uid = record['_id']
    return uid
  else:
    if '<' in email:
      name = capwords(email.split('<')[0].strip('"'))
      email = email.split('<')[1].rstrip('>').strip()
    else:
      name = email
    info = db.email.find_one({'email': email})
    if info:
      owner = info['owner']
      update_user(email, name=name, owner=owner)
      return owner
    else:
      update_user(email, name=name)
      return get_user_id_from_email_address(email)
  return email

def all_emails():
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  return db.email.find()

def update_user(email, name=None, owner=None, avatar=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  email = email.strip().lower()
  if owner:
    if db.owner.find_one({'email': email}):
      db.owner.update({'email': email}, {'$set': {'name': name,
                                                        'owner': owner}})
    else:
      db.owner.insert({'email': email,
                       'name': name,
                       'owner': owner,
                       '_id': new_id()})
  else:
    if db.owner.find_one({'email': email}):
      db.owner.update({'email': email}, {'$set': {'name': name}})
    else:
      db.owner.insert({'email': email, 'name': name, '_id': new_id()})
  
  cache.delete('%s:all_users' % db_name)
  return True
  
def update_record(collection, query, info):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  db[collection].update(query, {'$set': info})
  return True

def archive_post(session_id, post_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  db.stream.update({'_id': long(post_id)}, 
                   {'$push': {'archived_by': user_id}})
  clear_html_cache(post_id)  
  return True

def unarchive_post(session_id, post_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  db.stream.update({'_id': long(post_id)}, 
                   {'$pull': {'archived_by': user_id}})
  clear_html_cache(post_id)  
  return True

def archive_posts(session_id, ts):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  viewers = get_group_ids(user_id)
  viewers.append(user_id)
  db.stream.update({'viewers': {'$in': viewers},
                    'last_updated': {'$lte': ts}},  
                   {'$push': {'archived_by': user_id}}, multi=True)
  # TODO: clear cache?
  return True

def new_post_from_email(message_id, receivers, sender, 
                        subject, text, html, attachments,
                        date, ref=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id_from_email_address(sender)
  session_id = get_session_id(user_id)
  
  viewers = [get_user_id_from_email_address(i) for i in receivers]
  viewers.append(get_user_id_from_email_address(sender))
  
  ref_info = None
  if ref:
    ref_info = db.stream.find_one({'message_id': ref}, {'_id': True})
    if not ref_info:
      ref_info = db.stream.find_one({'comments.message_id': ref}, {'_id': True})
    
  if ref_info:
    message_ids = ref.split()
    for id in message_ids:
      info = db.stream.find_one({'comments.message_id': message_id})
      if not info:
        comment = {'_id': new_id(),
                   'owner': get_user_id_from_email_address(sender),
                   'message_id': message_id,
                   'receivers': receivers,
                   'sender': sender,
                   'body': Binary(str(text)),
                   'html': Binary(str(html)),
                   'timestamp': date}   
        if attachments:
          comment['attachments'] = attachments
        db.stream.update({'message_id': ref}, 
                         {'$push': {'comments': comment},
                          '$set': {'last_updated': utctime()},
                          '$unset': {'archived_by': 1}})
        
        
        parent = db.stream.find_one({'message_id': ref})
        if parent:
          clear_html_cache(parent['_id'])
          index_queue.enqueue(update_index, parent['_id'], 
                              text, viewers, is_comment=True, db_name=db_name)
          info = parent
          
          for id in info['viewers']:
            cache.clear(id)
            if is_group(id):
              push_queue.enqueue(publish, user_id, 
                                 '%s|unread-feeds' % id, info, db_name=db_name)
            else:
              push_queue.enqueue(publish, id, 
                                 'unread-feeds', info, db_name=db_name)
          
  else:
    if not db.stream.find_one({'message_id': message_id}):
      info = {'subject': Binary(str(subject)),
              'message_id': message_id,
              '_id': new_id(),
              'owner': get_user_id_from_email_address(sender),
              'viewers': viewers,
              'receivers': receivers,
              'sender': sender,
              'timestamp': date,
              'last_updated': date,
              'body': Binary(str(text)),
              'html': Binary(str(html))}
      if attachments:
        info['attachments'] = attachments
      db.stream.insert(info)
      text = '%s\n\n%s' % (subject, text)
      
      
      index_queue.enqueue(add_index, info['_id'], 
                          text, viewers, 'email', db_name)
  
      # send notification
      for id in viewers:
          cache.clear(id)
#        if not is_group(id) and id != user_id:
#          new_notification(session_id, id, 'message', info.get('_id'))
#          publish(id, 'unread-feeds', info)
#        else: # update last_updated
          db.owner.update({'_id': id},
                                {'$set': {'last_updated': utctime()}})
          push_queue.enqueue(publish, user_id, 
                             '%s|unread-feeds' % id, info, db_name=db_name)
          
  return True

def new_feed(session_id, message, viewers, 
             attachments=[], facebook_access_token=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not message:
    return False
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
    
  if 'public' in viewers:
    _viewers = set(['public'])
    viewers.remove('public')
  else:
    _viewers = set()
  
  if isinstance(message, dict): # system message
    mentions = []
  else:
    mentions = get_mentions(message)
  viewers.extend([i.get('id') for i in mentions])
    
  if isinstance(viewers, list):
    for i in viewers:
      if str(i).isdigit():
        _viewers.add(long(i))
      elif validate_email(i):
        _viewers.add(get_user_id_from_email_address(i))
        # TODO: send mail thông báo cho post owner nếu địa chỉ mail không tồn tại
      else:
        continue
  else:
    _viewers.add(long(viewers))
  
  viewers = set(_viewers)
  viewers.add(user_id)
  
  files = set()
  if attachments:
    if isinstance(attachments, list):
      for i in attachments:
        files.add(long(i))
    else:
      files.add(long(attachments))
  
  if not isinstance(message, dict): # system message
    hashtags = get_hashtags(message)
    update_hashtag(hashtags)
  else:
    hashtags = []
  
  ts = utctime()
  info = {'message': message,
          '_id': new_id(),
          'owner': user_id,
          'viewers': list(viewers),
          'hashtags': hashtags,
          'timestamp': ts,
          'last_updated': ts}
  if files:
    info['attachments'] = list(files)
  
  if not isinstance(message, dict): # system message
    urls = extract_urls(message)
    if urls:
      info['urls'] = urls
      for url in urls:
        crawler_queue.enqueue(get_url_description, url, db_name=db_name)
      
  db.stream.insert(info)
  
  index_queue.enqueue(add_index, info['_id'], message, viewers, 'post', db_name)
  
  
  # send notification
  for id in viewers:
    if not is_group(id) and id != user_id:
      notification_queue.enqueue(new_notification, 
                                 session_id, id, 'message', 
                                 ref_id=info.get('_id'), db_name=db_name)
      push_queue.enqueue(publish, id, 'unread-feeds', info, db_name=db_name)

      # send email
      u = get_user_info(id)
      
      if u.email and 'share_posts' not in u.disabled_notifications and '@' in u.email and (u.status == 'offline' or (u.status == 'away' and utctime() - u.last_online > 180)):
        send_mail_queue.enqueue(send_mail, u.email, mail_type='new_post',
                                user_id=user_id, post=info, db_name=db_name)

    elif id == user_id:
      push_queue.enqueue(publish, id, 'unread-feeds', info, db_name=db_name)
    else: # set group last_updated time
      db.owner.update({'_id': id},
                      {'$set': {'last_updated': utctime()}})
      push_queue.enqueue(publish, user_id, 
                         '%s|unread-feeds' % id, info, db_name=db_name)

      
  # clear wsgimiddleware cache
  user_ids = set()
  for i in viewers:
    if is_group(i):
      member_ids = get_group_member_ids(i)
      for id in member_ids:
        user_ids.add(id)
    else:
      user_ids.add(i)
  for user_id in user_ids:
    cache.clear(user_id)
  
  return info['_id']

def post_message_trello(service_name, message, viewers):
  try:
    db_name = get_database_name()
    db = DATABASE[db_name]
    if service_name == 'trello':
      email = 'trello@yahoo.com'
      user = db.owner.find_one({'email':email},
                               {'session_id':True})
      if not user:
        session_id = sign_up(email='trello@yahoo.com', 
                             password='thieuchuthieuchu', name='Trello')
        return None
      else:
        session_id = user['session_id']
        return new_feed(session_id, str(message), viewers=viewers)
#         return new_feed(session_id, str(message), viewers=['public'])
  except:
    return None


def add_id_trello_to_stream(id_post, id_card_trello):
  db_name = get_database_name()
  db = DATABASE[db_name]
  db.stream.update({'_id': id_post},
                   {'$set': {'id_card_trello': str(id_card_trello)}})

def comment_message_trello(message, id_card_trello):
  query = {'id_card_trello': str(id_card_trello)}
  db_name = get_database_name()
  db = DATABASE[db_name]
  info_stream = db.stream.find_one(query)
  if info_stream:
    ref_id = info_stream['_id']
    email = 'trello@yahoo.com'
    user = db.owner.find_one({'email':email},
                                 {'session_id':True})
    if user:
      session_id = user['session_id']
      new_comment(session_id, message, ref_id)




def set_viewers(session_id, feed_id, viewers):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  viewers.append(str(user_id))
  _viewers = set(viewers)
  viewers = []
  for _id in _viewers:
    if _id == 'public' or isinstance(_id, int) or isinstance(_id, long):
      viewers.append(_id)
    elif _id.isdigit():
      viewers.append(int(_id))  
  
  _id = long(feed_id)
  feed = db.stream.find_and_modify({'_id': _id, 'owner': user_id},
                                         {'$set': {'viewers': viewers}})
  if not feed:
    return False
  new_users = [i for i in viewers if not is_group(i) and i not in feed['viewers']]
  for i in new_users:
    if i != user_id:
      notification_queue.enqueue(new_notification, 
                                 session_id, i, 'message', 
                                 ref_id=_id, db_name=db_name)

  
  clear_html_cache(feed_id)
  index_queue.enqueue(update_viewers, feed_id, viewers, db_name)
  return True

def reshare(session_id, feed_id, viewers):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  viewers.append(str(user_id))
  viewers = set(viewers)
  
  print db_name
  
  _viewers = []
  for i in viewers:
    if str(i).isdigit():
      _viewers.append(long(i))
    elif validate_email(i) is True:
      _viewers.append(get_user_id_from_email_address(i))
    elif i == 'public':
      _viewers.append(i)
    else:
      continue
  
  
  viewers = _viewers

  group_ids = get_group_ids(user_id)
  group_ids.append(user_id)
  group_ids.append('public')
  
  _id = long(feed_id)
  ts = utctime()
  feed = db.stream.find_and_modify({'_id': _id, 'viewers': {'$in': group_ids}}, 
                                   {'$addToSet': {'viewers': {"$each": viewers}},
                                    '$set': {'last_updated': ts},
                                    '$push': {'history': {'owner': user_id,
                                                          'ref': viewers,
                                                          'action': 'forward',
                                                          'timestamp': ts}}})
  if not feed:
    return False
  new_users = [i for i in viewers if not is_group(i) and i not in feed['viewers']]
  for i in new_users:
    if i != user_id:
      notification_queue.enqueue(new_notification, 
                                 session_id, i, 'message', 
                                 ref_id=_id, db_name=db_name)
      
      u = get_user_info(i)
      send_mail_queue.enqueue(send_mail, 
                              u.email, mail_type='new_post', 
                              user_id=user_id, post=feed, db_name=db_name)
      
  index_queue.enqueue(update_viewers, feed_id, viewers, db_name)

  clear_html_cache(feed_id) 

  return True

def remove_feed(session_id, feed_id, group_id=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  post = get_feed(session_id, feed_id)
  
  if group_id:
    if str(group_id).isdigit():
      group_id = long(group_id)
    if is_admin(user_id, group_id):
      db.stream.update({'_id': long(feed_id)}, 
                       {'$pull': {'viewers': group_id}})
      return True
  
  elif not post.read_receipt_ids and user_id == post.owner.id:
    db.stream.update({'_id': long(feed_id)}, 
                     {'$set': {'is_removed': True}})
    
    for user_id in post.viewer_ids:
      push_queue.enqueue(publish, user_id, 'remove', 
                         {'post_id': str(feed_id)}, db_name=db_name)
      
    return True
  
  return False

def undo_remove(session_id, feed_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  db.stream.update({'_id': long(feed_id), 'owner': user_id}, 
                         {'$unset': {'is_removed': 1}})
  # TODO: chỉ cho xóa nếu chưa có ai đọc
  return feed_id

@line_profile
def get_feed(session_id, feed_id, group_id=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = db.stream.find_one({'_id': long(feed_id),
                             'is_removed': None})
  if not info or info.has_key('is_removed'):
    return Feed({})
  
  public = False
  if 'public' in info['viewers']:
    public = True
  else:
    for i in info.get('viewers'):
      if is_public(i):
        public = True
        break
  
  if info and public is True:
    return Feed(info, db_name=db_name)
  elif info:
    if group_id and group_id in info['viewers']:
      return Feed(info, db_name=db_name)
    else:
      user_id = get_user_id(session_id)
      viewers = get_group_ids(user_id)
      viewers.append(user_id)
      viewers.append('public')
      for i in viewers:
        if i in info['viewers']:
          return Feed(info, db_name=db_name)
  return Feed({})

def unread_count(session_id, timestamp):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  groups = db.owner.find({'members': user_id})
  group_ids = [i.get('_id') for i in groups]
  feeds = db.stream.find({'$or': [{'viewers': {'$in': group_ids}},
                                  {'owner': user_id}],
                          'timestamp': {'$gt': timestamp}}).count()
                                          
  docs = db.stream.find({'$or': [{'viewers': {'$in': group_ids}},
                                 {'owner': user_id}],
                         'timestamp': {'$gt': timestamp}}).count()
  return feeds + docs

@line_profile
def get_public_posts(session_id=None, user_id=None, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if user_id:
    feeds = db.stream.find({'is_removed': None,
                            'viewers': {'$all': [long(user_id), 'public']}})\
                     .sort('last_updated', -1)\
                     .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                     .limit(settings.ITEMS_PER_PAGE)
  else:
    query = {'is_removed': None,
             'viewers': 'public'}
    if session_id:
      user_id = get_user_id(session_id)
#      query['starred'] = {'$nin': [user_id]}
#      query['archived_by'] = {'$nin': [user_id]}
      
    feeds = db.stream.find(query).sort('last_updated', -1)\
                     .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                     .limit(settings.ITEMS_PER_PAGE)
  return [Feed(i, db_name=db_name) for i in feeds if i]

def get_shared_by_me_posts(session_id, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  feeds = db.stream.find({'is_removed': None,
                          'owner': user_id,
                          'viewers': 'public'}).sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(settings.ITEMS_PER_PAGE)
  return [Feed(i, db_name=db_name) for i in feeds if i]
  

def get_starred_posts(session_id, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  feeds = db.stream.find({'is_removed': None,
                          'starred': user_id}).sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(settings.ITEMS_PER_PAGE)
  return [Feed(i, db_name=db_name) for i in feeds if i]

def get_starred_posts_count(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  return db.stream.find({'is_removed': None,
                         'starred': user_id}).count()
  

def get_archived_posts(session_id, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  feeds = db.stream.find({'is_removed': None,
                          'message_id': None,
                          'archived_by': user_id})\
                   .sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(settings.ITEMS_PER_PAGE)
  return [Feed(i, db_name=db_name) for i in feeds if i]

def get_incoming_posts(session_id, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  following_users = get_following_users(user_id)
  starred_posts = db.stream.find({'starred': {'$in': following_users}})\
                                 .sort('last_updated', -1)\
                                 .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                                 .limit(settings.ITEMS_PER_PAGE)
                                 
  feeds = db.stream.find({'is_removed': None,
                          'message_id': None,
                          '$and': [{'viewers': 'public'},
                                   {'owner': {'$ne': user_id}},
                                   {'viewers': {'$in': following_users}}]
                          })\
                   .sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(settings.ITEMS_PER_PAGE)
  posts = list(feeds)
  post_ids = [i.get('_id') for i in posts]
  for post in starred_posts:
    if post.get('_id') not in post_ids:
      post_ids.append(post.get('_id'))
      posts.append(post)
  if posts:
    posts.sort(key=lambda k: k['last_updated'], reverse=True)
  return [Feed(i, db_name=db_name) for i in posts if i]

def get_discover_posts(session_id, page=1):
  """
  latest posts from you & followers
  """
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  following_users = get_following_users(user_id)
  following_users.append(user_id)
                                 
  feeds = db.stream.find({'is_removed': None,
                          'message_id': None,
                          '$or': [{'$and': [{'viewers': 'public'},
                                            {'viewers': {'$in': following_users}}]},
                                  {'starred': {'$in': following_users}}]
                          
                          })\
                   .sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(settings.ITEMS_PER_PAGE)
  return [Feed(i, db_name=db_name) for i in feeds]
  
  
def get_hot_posts(page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  feeds = db.stream.find({'is_removed': None,
                          'viewers': 'public'})\
                   .sort('last_updated', -1)\
                   .limit(100)
  feeds = list(feeds)
  feeds.sort(key=lambda k: get_score(k), reverse=True)

  feeds = feeds[((page-1)*settings.ITEMS_PER_PAGE):(page*settings.ITEMS_PER_PAGE)]
  return [Feed(i, db_name=db_name) for i in feeds if i]

def get_focus_feeds(session_id, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  feeds = db.stream.find({'is_removed': None,
                          'viewers': user_id,
                          'priority': {'$ne': None}})\
                   .sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(settings.ITEMS_PER_PAGE)
  return [Feed(i, db_name=db_name) for i in feeds]

def get_user_posts(session_id, user_id, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = long(user_id)
  owner_id = get_user_id(session_id)
#  groups_list_1 = get_group_ids(owner_id)
#  groups_list_2 = get_group_ids(user_id)
#  viewers = [i for i, j in zip(groups_list_1, groups_list_2) if i == j]
#  viewers.append('public')
#
#  feeds = db.stream.find({'$or': [{'owner': user_id, 'viewers': {'$in': viewers}}, 
#                                  {'$and': [{'viewers': user_id}, 
#                                            {'viewers': owner_id}]}],
#                          'is_removed': None})\
#                         .sort('last_updated', -1)\
#                         .skip((page - 1) * settings.ITEMS_PER_PAGE)\
#                         .limit(settings.ITEMS_PER_PAGE)
                         
                         
  feeds = db.stream.find({'$or': [{'viewers': 'public', 'owner': user_id},
                                  {'$and': [{'viewers': user_id}, 
                                            {'viewers': owner_id}]}],
                          'message.action': None,
                          'is_removed': None})\
                   .sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(settings.ITEMS_PER_PAGE)
                                        
  return [Feed(i, db_name=db_name) for i in feeds if i]

def get_user_notes(session_id, user_id, limit=3):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = long(user_id)
  owner_id = get_user_id(session_id)
  if not owner_id:
    return []
  groups_list_1 = get_group_ids(owner_id)
  groups_list_2 = get_group_ids(user_id)
  viewers = [i for i, j in zip(groups_list_1, groups_list_2) if i == j]
  viewers.append('public')

  notes = db.stream.find({'owner': user_id, 
                          'viewers': {'$in': viewers},
                          'version': {'$ne': None},
                          'is_removed': None})\
                   .sort('last_updated', -1)\
                   .limit(limit)                    
                                        
  return [Note(i) for i in notes if i]


def get_user_files(session_id, user_id, limit=3):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = long(user_id)
  owner_id = get_user_id(session_id)
  if not owner_id:
    return []
  groups_list_1 = get_group_ids(owner_id)
  groups_list_2 = get_group_ids(user_id)
  viewers = [i for i, j in zip(groups_list_1, groups_list_2) if i == j]
  viewers.append('public')

  files = db.stream.find({'owner': user_id, 
                          'viewers': {'$in': viewers},
                          'history.attachment_id': {'$ne': None},
                          'is_removed': None})\
                   .sort('last_updated', -1)\
                   .limit(limit)
                                        
  return [File(i) for i in files if i]

  
  
def get_emails(session_id, email_address=None, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  viewers = get_group_ids(user_id)
  viewers.append(user_id)
  feeds = db.stream.find({'is_removed': None,
                          'message_id': {'$ne': None},
                          'viewers': {'$in': viewers}})\
                   .sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(settings.ITEMS_PER_PAGE)
  return [Feed(i, db_name=db_name) for i in feeds if i]

def get_pinned_posts(session_id, category='default'):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  
  key = '%s:pinned_post' % category
  namespace = user_id
  out = cache.get(key, namespace)
  if out:
    return out
  
  feeds = db.stream.find({'is_removed': None,
                          'archived_by': {'$nin': [user_id]},
                          'pinned': user_id})\
                   .sort('last_updated', -1)
                           
  feeds = [Feed(i, db_name=db_name) for i in feeds if i]
  cache.set(key, feeds, 3600, namespace)
  return feeds


def get_direct_messages(session_id, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  query = {'$and': [{'viewers': user_id},
                    {'viewers': {'$nin': ['public']}}],
           'archived_by': {'$nin': [user_id]},
           'is_removed': None}
  feeds = db.stream.find(query)\
                           .sort('last_updated', -1)\
                           .skip((page - 1) * 5)\
                           .limit(5)
  return [Feed(i, db_name=db_name) for i in feeds]
  
@line_profile
def get_feeds(session_id, group_id=None, page=1, 
              limit=settings.ITEMS_PER_PAGE, include_archived_posts=False):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  key = '%s:%s:%s:%s' % (group_id, page, limit, include_archived_posts)
  out = cache.get(key, user_id)
  if out:
    return out
  
  if not user_id:
    if group_id:
      group = get_record(group_id, 'owner')
      if group.get('privacy') == 'open':
        feeds = db.stream.find({'is_removed': None,
                                'viewers': long(group_id)})\
                         .sort('last_updated', -1)\
                         .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                         .limit(limit)
        feeds = [Feed(i, db_name=db_name) for i in feeds if i]
        cache.set(key, feeds, 3600, user_id)
        return feeds
    return []

  if group_id:
    if str(group_id).isdigit():
      group_id = long(group_id)
    else:
      group_id = 'public'
    
    feeds = db.stream.find({'is_removed': None,
                            'viewers': group_id})\
                            .sort('last_updated', -1)\
                            .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                            .limit(limit)
      
  else:
    viewers = get_group_ids(user_id)
    viewers.append(user_id)
    
    query = {'viewers': {'$in': viewers},
             '$or': [{'comments': {'$ne': None}, 
                      'message.action': {'$ne': None}},                                 
                     {'message.action': None}],
             'is_removed': None}  
    if not include_archived_posts:
      query['archived_by'] = {'$nin': [user_id]}
        
    feeds = db.stream.find(query)\
                     .sort('last_updated', -1)\
                     .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                     .limit(limit)
                                    
  feeds = [Feed(i, db_name=db_name) for i in feeds if i]
  cache.set(key, feeds, 3600, user_id)
  return feeds

@line_profile
def get_unread_feeds(session_id, timestamp, group_id=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  if not group_id:
    viewers = get_group_ids(user_id)
    viewers.append(user_id)
  else:
    viewers = [group_id]
  
  feeds = db.stream.find({'viewers': {'$in': viewers},
                          'last_updated': {'$gt': timestamp}})\
                          .sort('last_updated', -1)
                                        
#  feeds = list(feeds)
#  feeds.sort(key=lambda k: k.get('last_updated'), reverse=True)
  return [Feed(i, db_name=db_name) for i in feeds]

@line_profile
def get_unread_posts_count(session_id, group_id, from_ts=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id, db_name=db_name)
  if not user_id:
    return 0
  
  group_id = long(group_id)
  group = get_group_info(session_id, group_id)
  if not group.id:
    return 0
  
#   get last viewed timestamp
  if from_ts:
    last_ts = float(from_ts)
  else:
    last_ts = 0
    records = group.to_dict().get('recently_viewed', [])
    records.reverse()
    for i in records:
      if not i:
        continue
      if i['user_id'] == user_id:
        last_ts = i['timestamp']
        break
#  
#  return db.stream.find({'viewers': group_id,
#                         'is_removed': {"$exists": False},
#                         'last_updated': {'$gt': last_ts}}).count()
  return db.stream.find({'viewers': group_id,
                         'owner': {'$ne': user_id},
                         'is_removed': None,
                         'last_updated': {'$gt': last_ts},
                         'message.action': None,
                         'read_receipts.user_id': {'$ne': user_id}}).count()
                  
  

# Task actions -----------------------------------------------------------------
def mark_resolved(session_id, task_id):
  """ Set status to 'resolved' """
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if user_id:    
    viewers = get_group_ids(user_id)
    viewers.append(user_id)
    
    ts = utctime()
    
    db.stream.update({"_id": task_id, "viewers": {'$in': viewers}}, 
                           {"$push": {'history': {"action": "mark as resolved",
                                                  "user_id": user_id,
                                                  "timestamp": ts}},
                            "$unset": {"archived_by": True},
                            "$set": {"status": 'resolved',
                                     "last_updated": ts}})
    clear_html_cache(task_id)
    return True
  return False


def mark_unresolved(session_id, task_id):
  """ Set status to 'unresolved' (only owner) """
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if user_id:
    ts = utctime()
    
    db.stream.update({"_id": task_id, "owner": user_id},
                           {"$push": {'history': {"action": "mark as unresolved",
                                                  "user_id": user_id,
                                                  "timestamp": ts}},
                            "$unset": {"archived_by": True},
                            "$set": {"status": 'unresolved',
                                     "last_updated": ts}})
    clear_html_cache(task_id)
    return True
  return False


def restore(session_id, task_id):
  """ Set status to 'unresolved' (only owner) """
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if user_id:
    ts = utctime()
    
    db.stream.update({"_id": task_id, "owner": user_id},
                           {"$push": {'history': {"action": "restore",
                                                  "user_id": user_id,
                                                  "timestamp": ts}},
                            "$unset": {"archived_by": True},
                            "$set": {"status": 'unresolved',
                                     "last_updated": ts}})
    clear_html_cache(task_id)
    return True
  return False

def mark_cancelled(session_id, task_id):
  """ Set status to 'cancelled' (only owner) """
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if user_id:
    ts = utctime()
    
    db.stream.update({"_id": task_id, "owner": user_id},
                           {"$push": {'history': {"action": "mark as cancelled",
                                                  "user_id": user_id,
                                                  "timestamp": ts}},
                            "$unset": {"archived_by": True},
                            "$set": {"status": 'cancelled',
                                     "last_updated": ts}})
    clear_html_cache(task_id)
    return True
  return False
  

# Comment Actions --------------------------------------------------------------

def new_comment(session_id, message, ref_id, 
                attachments=None, reply_to=None, from_addr=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
#  if not message:
#    return False

  user_id = get_user_id(session_id, db_name=db_name)
  if not user_id:
    return False
  
  ts = utctime()
  comment = {'_id': new_id(),
             'owner': user_id,
             'message': message,
             'timestamp': ts}    
  
  files = []
  if attachments:
    if isinstance(attachments, list):
      for i in attachments:
        files.append(long(i))
    else:
      files.append(long(attachments))
  if files:
    comment['attachments'] = files
    
  if reply_to:
    comment['reply_to'] = long(reply_to)
  
  mentions = get_mentions(message)
  mentions = [long(i.get('id')) for i in mentions]
  mentions.append(user_id)
  mentions = list(set(mentions))
  
  # send notification
  info = db.stream.find_one({'_id': long(ref_id)})
  if not info:
    return False
  
  owner_id = info.get('owner')
  viewers = info.get('viewers')
  
  new_mentions = [i for i in mentions if i not in viewers and i != user_id]

  if user_id != owner_id:
    notification_queue.enqueue(new_notification, 
                               session_id, owner_id, 'comment', 
                               ref_id=ref_id, comment_id=comment['_id'], db_name=db_name)
    
  db.stream.update({"_id": long(ref_id)}, 
                   {"$push": {"comments": comment},
                    "$addToSet": {'viewers': {"$each": mentions}},
                    "$set": {'last_updated': ts},
                    '$unset': {'archived_by': 1}})
  
  
  
  info['last_updated'] = ts
  info['archived_by'] = []
  viewers.extend(mentions)
  viewers.append(info['owner'])
  info['viewers'] = set(viewers)
  if info.has_key('comments'):
    info['comments'].append(comment)
  else:
    info['comments'] = [comment]
    
  # TODO: reply to notification?
    
  
  for uid in mentions:
    if uid != user_id:
      notification_queue.enqueue(new_notification, 
                                 session_id, uid, 'mention', 
                                 ref_id=ref_id, comment_id=comment['_id'], db_name=db_name)
      u = get_user_info(uid)
      if u.email and 'mentions' not in u.disabled_notifications:
        send_mail_queue.enqueue(send_mail, u.email, 
                                mail_type='mentions', 
                                user_id=user_id, post=info, 
                                db_name=db_name)
    
  
  receivers = [info.get('owner')]
  if info.get('comments'):
    for i in info.get('comments'):
      if i.get('owner') != user_id and i.get('owner') not in mentions and i.get('owner') not in receivers:
        receivers.append(i.get('owner'))
        notification_queue.enqueue(new_notification, 
                                   session_id, 
                                   i.get('owner'), 
                                   'comment', 
                                   ref_id=ref_id, 
                                   comment_id=comment['_id'], 
                                   db_name=db_name)
        
  owner = get_user_info(user_id)
  if owner.email and '@' in owner.email and 'comments' not in owner.disabled_notifications and user_id not in mentions:
    if owner.status == 'offline' or (owner.status == 'away' and utctime() - owner.last_online > 180):
      send_mail_queue.enqueue(send_mail, owner.email, 
                              mail_type='new_comment', 
                              user_id=user_id, post=info, 
                              db_name=db_name)

  for id in info['viewers']:
    cache.clear(id)
    if is_group(id):
      push_queue.enqueue(publish, user_id, 
                         '%s|unread-feeds' % id, info, db_name=db_name)
    else:
      push_queue.enqueue(publish, id, 'unread-feeds', info, db_name=db_name)
      
      
#       if user_id != id and id not in mentions:
#         # send email notification
#         u = get_user_info(id)
#         if u.email and '@' in u.email and 'comments' not in u.disabled_notifications:
#           if u.status == 'offline' or (u.status == 'away' and utctime() - u.last_online > 180):
#             send_mail_queue.enqueue(send_mail, u.email, 
#                                     mail_type='new_comment', 
#                                     user_id=user_id, post=info, 
#                                     db_name=db_name)
  
  urls = extract_urls(message)
  if urls:
    for url in urls:
      crawler_queue.enqueue(get_url_description, url, db_name=db_name)
      
  index_queue.enqueue(update_index, ref_id, 
                      message, viewers, is_comment=True, db_name=db_name)
  
  # upate unread notifications
  mark_notification_as_read(session_id, ref_id=ref_id)
  
  unread_notifications_count = get_unread_notifications_count(user_id,
                                                              db_name=db_name)
  push_queue.enqueue(publish, user_id, 'unread-notifications', 
                     unread_notifications_count, db_name=db_name)
  
  
  clear_html_cache(ref_id)
  
  comment['post_id'] = ref_id 
  
  r = Comment(comment, db_name=db_name)
  for i in info['comments'][::-1]:
    if i['_id'] == reply_to:
      r.reply_src = Comment(i, db_name=db_name)
      break
  
  return r

def remove_comment(session_id, comment_id, post_id=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  comment_id = long(comment_id)
  
  record = db.stream.find_and_modify({'$and': [{'comments.owner': user_id},
                                               {'comments._id': comment_id}]},
                                     {'$set': {'comments.$.is_removed': True}})
  if not record:
    record = db.stream.find_and_modify({'$and': [{'owner': user_id},
                                                 {'comments._id': comment_id}]},
                                       {'$set': {'comments.$.is_removed': True}})
  
  for _id in record.get('viewers'):
    cache.clear(_id)
    push_queue.enqueue(publish, _id, 'unread-notifications', 
                       get_unread_notifications_count(user_id, db_name=db_name), 
                       db_name=db_name)
                  
    # Note: phải ép comment_id về str vì javascript không xử lý được số int lớn 
    # như số id của comment_id (id do snowflake sinh ra)
    push_queue.enqueue(publish, _id, 'remove', 
                       {'comment_id': str(comment_id)}, db_name=db_name)
  clear_html_cache(record['_id'])
    
  return True

def diff(text1, text2):
  if isinstance(text1, basestring):
    if not isinstance(text1, unicode):
      text1 = unicode(text1, 'utf-8')
  if isinstance(text2, basestring):
    if not isinstance(text2, unicode):
      text2 = unicode(text2, 'utf-8')
  
  diffs = dmp.diff_main(text1, text2)

  html = ''
  for i in diffs:
    if i[0] == -1:
      html += '<span class="diff x">%s</span>' % i[1]
    elif i[0] == 1:
      html += '<span class="diff i">%s</span>' % i[1]
    else:
      html += '<span>%s</span>' % i[1]
  return html.encode('utf-8')


def update_post(session_id, post_id, message):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  record = db.stream.find_and_modify({'_id': long(post_id), 'owner': user_id},
                                     {"$set": {"new_message": message,
                                               "last_edited": utctime()}})
  
  if not record:
    return False
  
  # TODO: push changes?
  for _id in record.get('viewers', []):
    cache.clear(_id)

  clear_html_cache(record['_id'])
    
  return True
  
  


def update_comment(session_id, comment_id, message, post_id=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
    
  # TODO: lưu history các lần chỉnh sửa?
  record = db.stream.find_and_modify({'$and': [{"comments.owner": user_id}, 
                                               {"comments._id": long(comment_id)}]},
                                     {"$set": {"comments.$.new_message": message,
                                               "comments.$.last_edited": utctime()}})

  if not record:
    return False
  
  text = filters.sanitize_html(\
                filters.nl2br(\
                       filters.autoemoticon(\
                              filters.autolink(message))))
  
  for comment in record['comments']:
    if comment['_id'] == comment_id:
      original_message = comment['message']
      
  for _id in record.get('viewers'):
    cache.clear(_id)
    
    # Note: phải ép comment_id về str vì javascript không xử lý được số int lớn 
    # như số id của comment_id (id do snowflake sinh ra)
    push_queue.enqueue(publish, _id, 
                       'update', {'comment_id': str(comment_id),
                                  'text': text,
                                  'changes': diff(original_message, message)}, 
                       db_name=db_name)

  clear_html_cache(record['_id'])
  return True


#def get_comment(session_id, comment_id):
#  user_id = get_user_id(session_id)
#  if not user_id:
#    return False
#  
#  info = db.comment.find_one({'_id': long(comment_id)})
#  return Comment(info)
#
#def get_comments(session_id, post_id, page=1, page_size=10):
#  user_id = get_user_id(session_id)
#  if not user_id:
#    return False
#  
#  records = db.comment.find({'post_id': long(post_id), 'owner': user_id})\
#                            .sort('timestamp', -1)\
#                            .skip(page-1*page_size)\
#                            .limit(page_size)
#  return [Comment(i) for i in records]
  

def hide_as_spam(session_id, ref_id, comment_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  collection, uuid = ref_id.split(':')
  owner_id = get_user_id(session_id)
  if not owner_id:
    return False
  
  db[collection].update({"_id": uuid, 
                               "owner": owner_id, 
                               "comments._id": comment_id},
                              {"$set": {"comments.$.is_spam": 1}})
      
  return True

def not_spam(session_id, ref_id, comment_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  collection, uuid = ref_id.split(':')
  owner_id = get_user_id(session_id)
  if not owner_id:
    return False
  
  db[collection].update({"_id": uuid, 
                               "owner": owner_id,
                               "comments._id": comment_id},
                              {"$unset": {"comments.$.is_spam": 1}})
      
  return True


# Docs Actions -----------------------------------------------------------------

def remove_html_tags(data):
  data = data.replace('<br>', '\n')
  p = re.compile(r'<.*?>')
  out = p.sub('', data)
  html_codes = (
    ('&', '&amp;'),
    ('<', '&lt;'),
    ('>', '&gt;'),
    ('"', '&quot;'),
    ("'", '&#39;'),
  )
  
  for code in html_codes:
    out = out.replace(code[1], code[0])
  return out

def html_escape(text):
  html_escape_table = {"&": "&amp;",
                       '"': "&quot;",
                       "'": "&apos;",
                       ">": "&gt;",
                       "<": "&lt;"}
  return "".join(html_escape_table.get(c,c) for c in text)

def compare_with_previous_version(session_id, doc_id, revision):
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  info = get_note(session_id, doc_id).to_dict()
  if not info:
    return False
  
  version = info.get('version')
  version.reverse()
  try:
    prev_content = info.get('version')[revision + 1].get('content')
  except IndexError:
    prev_content = None
  content = info.get('version')[revision].get('content')  
  
  def set_style(text, action):
    if action == 'remove':
      cls = 'x'
    elif action == 'insert':
      cls = 'i'
    else:
      return text
    return '<span class="diff %s"><span>%s</span></span>' % (cls, text)
      
  if prev_content:
    content = htmldiff(prev_content, content)
  else:
    content = set_style(content, 'insert')
  
  try:
    prev_title = info.get('version')[revision+1].get('title', 'Untitled Noted')
  except:
    prev_title = None
  title = info.get('version')[revision].get('title', 'Untitled Noted')
  if prev_title:
    title = htmldiff(prev_title, title)
  else:
    title = set_style(title, 'insert')
      
  doc = Note(info)
  start = revision - 2
  end = revision + 3
  if start < 0:
    start = 0
    end = start + 5
  while end > len(version):
    end -= 1
    start = end - 5
  version = version[start:end]
  doc.version = [Version(i) for i in version]
  doc.content = content
  doc.title = title
  doc.timestamp = version[revision].get('timestamp')
  doc.owner = get_user_info(version[revision].get('owner'))
  doc.additions = doc.content.count('class="i"')
  doc.deletions = doc.content.count('class="x"')
  return doc


def compare_with_current_version(session_id, doc_id, revision):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  info = db.stream.find_one({'$or': [{'viewers': user_id},
                                        {'owner': user_id}], 
                                 '_id': doc_id})
  version = info.get('version')
  version.reverse()
  current_version = info.get('version')[0].get('content')
  compare_version = info.get('version')[revision].get('content')
  
  def set_style(text, type):
    if type == 'remove':
      cls = 'x'
    elif type == 'insert':
      cls = 'i'
    else:
      return text
    return '<span class="%s"><span>%s</span></span>' % (cls, text)
  
  diffs = dmp.diff_main(compare_version, current_version, checklines=True)

  html = []
  for diff in diffs:
    state, text = diff
    if state == -1:
      html.append(set_style(text, 'remove'))
    elif state == 1:
      html.append(set_style(text, 'insert'))
    else:
      html.append(set_style(text, 'normal'))
      
  content = ''.join(html)
  
  title, content = content.split('\n', 1)
  doc = Doc(info)
  doc.version = [Version(i) for i in version[:5]]
  doc.content = content
  doc.title = title
  doc.timestamp = isoformat(version[revision].get('timestamp'))
  doc.datetime = datetime_string(version[revision].get('timestamp'))
  owner_info = get_user_info(version[revision].get('owner'))
  doc.owner_name = owner_info.name
  doc.owner_avatar = owner_info.avatar
  return doc

def diff_stat(doc_id):  
  info = get_record(doc_id)
  version = info.get('version')
  version.reverse()
  try:
    previous_version = info.get('version')[1].get('content')
  except IndexError:
    previous_version = None
  compare_version = info.get('version')[0].get('content')  
  
  
  if previous_version:     
    
    content = htmldiff(previous_version, compare_version)
    additions = content.count('<ins>')
    deletions = content.count('<del>')
    
#    diffs = dmp.diff_main(html_escape(previous_version), 
#                          html_escape(compare_version), checklines=True)
#  
#    html = []
#    for diff in diffs:
#      state, text = diff
#      if state == -1:
#        deletions += 1
#      elif state == 1:
#        additions += 1
        
  else:
    additions = compare_version.count('\n')
    deletions = 0
      
  return {'additions': additions,
          'deletions': deletions}

def restore_doc(session_id, doc_id, revision):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not isinstance(revision, int):
    return False
  info = db.stream.find_one({'$or': [{'viewers': user_id},
                                        {'owner': user_id}], 
                                 '_id': doc_id})
  version = info.get('version')
  version.reverse()
  doc = version[revision]

  doc_id = update_note(session_id, doc_id, doc.get('content'), doc.get('tags'))
  return doc_id

def get_note(session_id, note_id, version=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = db.stream.find_one({'_id': long(note_id),
                             'is_removed': None})
  if not info or info.has_key('is_removed'):
    return Note({})
  
  public = False
  if 'public' in info['viewers']:
    public = True
  else:
    for i in info.get('viewers'):
      if is_public(i):
        public = True
        break
  
  if info and public is True:
    return Note(info, db_name=db_name)
  elif info:
    user_id = get_user_id(session_id)
    viewers = get_group_ids(user_id)
    viewers.append(user_id)
    viewers.append('public')
    for i in viewers:
      if i in info['viewers']:
        if version:
          version = version - 1 # python list index start from 0
        else:
          version = len(info['version']) - 1
        return Note(info, version=version, db_name=db_name)
  return Note({})


def get_docs_count(group_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if str(group_id).isdigit():
    group_id = long(group_id)
  else:
    group_id = 'public'
  return db.stream.find({'is_removed': None,
                         'viewers': group_id,
                         'version': {"$ne": None}}).count()


def get_notes(session_id, group_id=None, limit=5, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return []
  
  if group_id:
    members = get_group_member_ids(group_id)
    if user_id not in members:
      return []
    
    if str(group_id).isdigit():
      group_id = long(group_id)
    else:
      group_id = 'public'
  
    notes = db.stream.find({'is_removed': None,
                            'viewers': group_id,
                            'version': {'$ne': None}})\
                     .sort('last_updated', -1)\
                     .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                     .limit(limit)
  else:    
    notes = db.stream.find({'is_removed': None,
                            'version.owner': user_id})\
                     .sort('last_updated', -1)\
                     .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                     .limit(limit)
  return [Note(i) for i in notes]
    

def get_reference_notes(session_id, limit=10, page=1):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  viewers = get_group_ids(user_id)
  viewers.append(user_id)
   
  notes = db.stream.find({'is_removed': None,
                          'viewers': {'$in': viewers},
                          '$and': [{'version': {'$ne': None}}, 
                                   {'version.owner': {'$ne': user_id}}]
                          })\
                   .sort('last_updated', -1)\
                   .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                   .limit(limit)
  return [Note(i) for i in notes]


def get_drafts(session_id, page=1, limit=settings.ITEMS_PER_PAGE):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  docs = db.stream.find({'is_removed': None,
                         'viewers': [user_id], 
                         'version': {'$ne': None}})\
                  .sort('last_updated', -1)\
                  .skip((page - 1) * settings.ITEMS_PER_PAGE)\
                  .limit(limit)
  return [Doc(i) for i in docs]

  
def new_note(session_id, title, content, attachments=None, viewers=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  viewers = [long(i) if str(i).isdigit() else 'public' for i in viewers]
  
  viewers.append(user_id)
  viewers = list(set(viewers))
  
  info = {'_id': new_id(),
          'version': [{'title': title,
                       'content': content,
                       'timestamp': utctime(),
                       'owner': user_id}],
          'viewers': viewers,
          'owner': user_id,
          'timestamp': utctime(),
          'last_updated': utctime()}
  
  if attachments:
    attachments = [long(attachment_id) for attachment_id in attachments]
    info['attachments'] = attachments
  
  db.stream.insert(info)
  
  index_queue.enqueue(add_index, info['_id'], 
                      '%s\n\n%s' % (title, content), 
                      viewers, 'doc', db_name)
  
  # clear cache
  user_ids = set()
  for i in viewers:
    if is_group(i):
      member_ids = get_group_member_ids(i)
      for id in member_ids:
        user_ids.add(id)
    else:
      user_ids.add(i)
  for user_id in user_ids:
    cache.clear(user_id)
  
  return info['_id']

def update_note(session_id, doc_id, title, content, attachments=None, viewers=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  
  viewers = [long(u) if u != 'public' else 'public' for u in viewers if u]
  viewers.append(user_id)
  viewers = list(set(viewers))
  
  ts = utctime()
  
  info = {'timestamp': ts,
          'last_updated': ts}
  if attachments:
    attachments = [long(attachment_id) for attachment_id in attachments]
    info['attachments'] = attachments
    
  members = get_group_ids(user_id)
  members.append(user_id)
  
  query = {"$set": info,
           "$unset": {'archived_by': 1},
           "$addToSet": {'viewers': {'$each': viewers}},
           "$push": {'version': {'title': title,
                                 'content': content,
                                 'timestamp': utctime(),
                                 'owner': user_id},
                     'history': {'owner': user_id,
                                 'action': 'updated',
                                 'timestamp': utctime()}}}
  if not attachments:
    query['$unset'] = {'archived_by': 1, 'attachments': 1}
  
  db.stream.update({'_id': doc_id, 'viewers': {'$in': members}}, query)
  
  index_queue.enqueue(update_index, doc_id, 
                      '%s\n\n%s' % (title, content), 
                      viewers, db_name=db_name)
  
  receivers = [i for i in viewers if not is_group(i)]
  for receiver in receivers:
    if receiver != user_id:
      notification_queue.enqueue(new_notification, 
                                 session_id, receiver, 
                                 type='update', ref_id=doc_id, db_name=db_name)
      
  clear_html_cache(doc_id)
  
  return True

def remove_doc(session_id, doc_id):
  return remove_feed(session_id, doc_id)
  

def mark_official(session_id, doc_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  ts = utctime()
  db.stream.update({'_id': doc_id, 'viewers': user_id},
                         {'$set': {'is_official': True, 'last_updated': ts},
                          '$push': {'history': {'user_id': user_id,
                                                'action': 'mark official',
                                                'timestamp': ts}}})
  clear_html_cache(doc_id)
  return True

def mark_unofficial(session_id, doc_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  ts = utctime()
  db.stream.update({'_id': doc_id, 'viewers': user_id},
                         {'$unset': {'is_official': 1},
                          '$set': {'last_updated': ts},
                          '$push': {'history': {'user_id': user_id,
                                                'action': 'mark unofficial',
                                                'timestamp': ts}}})
  clear_html_cache(doc_id)
  return True
  
def get_key(session_id, doc_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  note = get_note(session_id, doc_id)
  if not note:
    return None
  
  if note.id and not note.key:
    id = _get_next_id()
    key = encode_url(id)
    db.stream.update({'_id': doc_id},
                           {'$set': {'key': key}})
    return key
  else:
    return note.key
  
def get_doc_by_key(key):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = db.stream.find_one({'key': key})
  return Note(info)


    
def _get_next_id():
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  result = db.command(SON({'findandmodify': 'id'},
                                query={'_id': 'auto_incr'},
                                update={'$inc': {'counter': 1}},
                                upsert=True))
  return result['value'].get('counter', 0)


# Reminders --------------------------------------------------------------------
def new_reminder(session_id, message):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  info = {'_id': new_id(),
          'owner': user_id,
          'message': message,
          'timestamp': utctime()}
  db.reminder.insert(info)
  return info['_id']

def check(session_id, reminder_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  db.reminder.update({'_id': int(reminder_id), 'owner': user_id},
                     {'$set': {'checked': True,
                               'last_updated': utctime()}})
  return True

def uncheck(session_id, reminder_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  db.reminder.update({'_id': int(reminder_id), 'owner': user_id},
                     {'$set': {'last_updated': utctime()},
                      '$unset': {'checked': True}})
  return True

def get_reminders(session_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  reminders = db.reminder.find({'owner': user_id, 
                                'checked': None})\
                         .sort('timestamp', -1)
  reminders = list(reminders)
  completed_list = db.reminder.find({'owner': user_id, 'checked': True})\
                              .sort('last_updated', -1)\
                              .limit(1)
  reminders.extend(completed_list)
  return [Reminder(i) for i in reminders]
    


# Event Actions ----------------------------------------------------------------
def new_event(session_id, name, when, 
              where=None, duration=None, details=None, viewers=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  # TODO: allow file attachments? 
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  
  if viewers:
    viewers = [long(u) if u != 'public' else 'public' for u in viewers if u]
  else:
    viewers = []
  viewers.append(user_id)
  viewers = list(set(viewers))
  info = {'_id': new_id(),
          'name': name,
          'when': when,
          'owner': get_user_id(session_id),
          'viewers': viewers,
          'timestamp': utctime(),
          'last_updated': utctime()}
  if duration:
    duration = float(duration)
    info['duration'] = duration
  if details:
    info['details'] = details
  if where:
    info['where'] = where
  event_id = db.stream.insert(info)
  return event_id

def get_event(session_id, event_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
    
  viewers = get_group_ids(user_id)
  viewers.append(user_id)
  viewers.append('public')
  info = db.stream.find_one({'_id': long(event_id),
                                   'viewers': {'$in': viewers}})
  return Event(info)

def get_events(session_id, group_id=None, as_feeds=False):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  if group_id:
    events = db.stream.find({'viewers': long(group_id), 
                             'is_removed': None,
                             'when': {"$ne": None}}).sort('when')
  else:
    viewers = get_group_ids(user_id)
    viewers.append(user_id)
    events = db.stream.find({'viewers': {'$in': viewers},
                             'is_removed': None,
                             'when': {'$ne': None}}).sort('when')
  if as_feeds:
    return [Feed(i, db_name=db_name) for i in events]
  return [Event(i) for i in events]
  
def get_upcoming_events(session_id, group_id=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    if group_id:
      group = get_record(group_id, 'owner')
      if group.get('privacy') == 'open':
        events = db.stream.find({'viewers': long(group_id), 
                                 'is_removed': None,
                                 'when': {"$gte": utctime()}})\
                          .sort('when')
    return []
  if group_id:
    events = db.stream.find({'viewers': long(group_id), 
                             'is_removed': None,
                             'when': {"$gte": utctime()}}).sort('when')
  else:
    viewers = get_group_ids(user_id)
    viewers.append(user_id)
    events = db.stream.find({'viewers': {'$in': viewers},
                             'is_removed': None,
                             'when': {'$gte': utctime()}}).sort('when')
  return [Event(i) for i in events]

def get_file_info(session_id, file_id):  
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)  
  viewers = get_group_ids(user_id)
  viewers.append(user_id)
  viewers.append('public')
  info = db.stream.find_one({'_id': long(file_id),
                                   'viewers': {'$in': viewers}})
  return File(info)

def get_attachment_info(attachment_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not is_snowflake_id(attachment_id):
    return Attachment({})
  key = '%s:info' % attachment_id
  info = cache.get(key)
  if not info:
    info = db.attachment.find_one({'_id': long(attachment_id)})
    cache.set(key, info)
  return Attachment(info) if info else Attachment({})

def get_viewers(post_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = db.stream.find_one({'_id': long(post_id)})
  if info:
    return [str(u) for u in info.get('viewers', [])]
  return []
  
  
def get_fid(md5_hash):
  db_name = get_database_name()
  db = DATABASE[db_name]
  datastore = GridFS(db)
  
  try:
    info = datastore.get_last_version(md5_hash)
    return info._id
  except NoFile:
    return None
  
def new_attachment(session_id_or_user_id, filename, filedata):
  db_name = get_database_name()
  db = DATABASE[db_name]
  datastore = GridFS(db)
  
  if isinstance(session_id_or_user_id, int) \
  or isinstance(session_id_or_user_id, long) \
  or session_id_or_user_id.isdigit():
    user_id = long(session_id_or_user_id)
  else:
    user_id = get_user_id(session_id_or_user_id)
    if not user_id:
      return False
  md5_hash = hashlib.md5(filedata).hexdigest()
  content_type = mimetypes.guess_type(filename)[0]
  if not content_type:
    content_type = 'application/octet-stream'
  fid = get_fid(md5_hash)
  if not fid and not is_s3_file(filename):
    fid = datastore.put(filedata, 
                        content_type=content_type,
                        filename=md5_hash)
    move_to_s3_queue.enqueue(move_to_s3, fid, db_name)
  
  info = {'_id': new_id(),
          'name': filename,
          'size': len(filedata),
          'md5': md5_hash,
          'owner': user_id,
          'timestamp': utctime()}
  if fid:
    info['fid'] = fid
  attachment_id = db.attachment.insert(info)
  return attachment_id

#TODO: locked attachment if attached
  
def new_file(session_id, attachment_id, viewers=None):    
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  if viewers:
    viewers = [long(user) if user != 'public' else 'public' \
               for user in viewers]
  else:
    viewers = []
  viewers.append(user_id)
  viewers = list(set(viewers))
  
  info = {'_id': new_id(),
          'owner': user_id,
          'viewers': viewers,
          'timestamp': utctime(),
          'last_updated': utctime(),
          'history': [{'attachment_id': long(attachment_id),
                       'owner': user_id,  
                       'timestamp': utctime()}]
          }
      
  file_id = db.stream.insert(info)
  
  name = get_attachment_info(attachment_id).name
  
  index_queue.enqueue(add_index, file_id, name, viewers, 'file', db_name)
  
  return file_id

def add_viewers(viewers, ref_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  viewers = [long(user) for user in viewers]
  db.stream.update({'_id': long(ref_id)}, 
                         {"$addToSet": {'viewers': {"$each": viewers}}})
  clear_html_cache(ref_id)
  return True

def rename_file(session_id, file_id, new_name):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  viewers = get_group_ids(user_id)
  viewers.append(user_id)
  viewers.append('public')
  
  ts = utctime()
  db.stream.update({'_id': file_id, 'viewers': {'$in': viewers}},
                         {'$set': {'filename': new_name,
                                   'last_updated': ts},
                          '$unset': {'archived_by': True},
                          '$push': {'history': {'user_id': user_id,
                                                'action': 'renamed',
                                                'timestamp': ts}}})
  clear_html_cache(file_id)
  return True

def update_file(session_id, file_id, attachment_id, viewers=[]):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  attachment_id = long(attachment_id)
  file_id = long(file_id)
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  if viewers:
    _viewers = []
    for id in viewers:
      if id == 'public':
        _viewers.append(id)
      else:
        try:
          _viewers.append(long(id))
        except AttributeError:
          continue
    viewers = _viewers
    db.stream.update({'_id': file_id, 'viewers': user_id},
                           {'$set': {'last_updated': utctime(),
                                     'viewers': viewers},
                            '$unset': {'archived_by': True},
                            '$push': {'history': 
                                      {'attachment_id': attachment_id,
                                       'owner': user_id,
                                       'timestamp': utctime()}}})
    
  else:
    
    db.stream.update({'_id': file_id, 'viewers': user_id},
                           {'$set': {'last_updated': utctime()},
                            '$unset': {'archived_by': True},
                            '$push': {'history': {'attachment_id': attachment_id,
                                                  'owner': user_id,
                                                  'timestamp': utctime()}}})
    viewers = db.stream.find_one({'_id': file_id}).get('viewers')
  
  clear_html_cache(file_id)
  
  return file_id

def get_file_data(attachment_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  datastore = GridFS(db)
  
  info = get_attachment_info(attachment_id)
  if info.md5 and is_s3_file(info.md5):
    k = Key(BUCKET)
    k.name = info.md5
    filedata = k.get_contents_as_string()
  else:
    f = datastore.get(info.fid)
    filedata = f.read()
  if not info.md5:
    db.attachment.update({'_id': long(attachment_id)},
                         {'$set': 
                          {"md5": hashlib.md5(filedata).hexdigest()}})
    key = '%s:info' % attachment_id
    cache.delete(key)
  return filedata


def get_attachment(attachment_id, db_name=None):
  if not db_name:    
    db_name = get_database_name()
  db = DATABASE[db_name]
  datastore = GridFS(db)
  
  info = db.attachment.find_one({'_id': long(attachment_id)})
  if not info:
    return False  
    
  fid = info.get('fid')
  filename = info.get('name')
  
  if datastore.exists(fid):
    f = datastore.get(fid)
    f._filename = filename
    f.owner = info.get('owner')
    return f
    
  elif info.has_key('md5'):
    content_type = mimetypes.guess_type(filename)[0]
    if content_type and content_type.startswith('image/'):
      url = s3_url(info.get('md5'), content_type=content_type)
    else:
      url = s3_url(info.get('md5'), 
                   content_type=content_type,
                   disposition_filename=filename)
    return url
  
  return False
    
  
def remove_attachment(session_id, attachment_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  # remove metadata
  db.attachment.remove({'_id': long(attachment_id), 
                              'owner': user_id})
  # TODO: remove file   
  return True

def get_files(session_id, group_id=None, limit=5):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  if not group_id:
    viewers = get_group_ids(user_id)
    viewers.append(user_id)
  else:
    group = get_group_info(session_id, group_id)
    if not group.id:
      return False
    viewers = [group.id]
  
  files = db.stream.find({'history.attachment_id': {'$ne': None},
                          'viewers': {'$in': viewers}})\
                   .sort('last_updated', -1)\
                   .limit(limit)
  return [File(f) for f in files]

def get_files_count(group_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if str(group_id).isdigit():
    group_id = long(group_id)
  else:
    group_id = 'public'
  return db.stream.find({'viewers': group_id,
                         'history.attachment_id': {"$ne": None}}).count()

def get_attachments(session_id, group_id=None, limit=10):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  if group_id:
    if str(group_id).isdigit():
      viewers = [long(group_id)]
    else:
      viewers = ['public']
  else:
    viewers = get_group_ids(user_id)
    viewers.append(user_id)
  
  if group_id:
    posts = db.stream.find({'$or': [{'history.attachment_id': {'$ne': None}},
                                    {'attachments': {'$ne': None}},
                                    {'comments.attachments': {'$ne': None}}], 
                            'viewers': {'$in': viewers}})\
                     .sort('last_updated', -1)\
                     .limit(limit)
  else:
    posts = db.stream.find({'$or': [{'attachments': {'$ne': None}},
                                    {'comments.attachments': {'$ne': None}}], 
                            'viewers': {'$in': viewers}})\
                     .sort('last_updated', -1)\
                     .limit(limit)
    
  attachments = []
  ids = set() 
  for post in posts:
    if post.has_key('attachments'):
      for i in post.get('attachments', []):
        if i not in ids:
          ids.add(i)
          info = get_attachment_info(i)
          info.rel = str(post.get('_id'))
          attachments.append(info)
          
    elif group_id and post.has_key('history') and post['history'][0].has_key('attachment_id'):
      for i in post['history'][::-1]:
        if i.has_key('attachment_id'):
          attachment_id = i.get('attachment_id')
          break
      
      if attachment_id not in ids:
        ids.add(attachment_id)
        info = get_attachment_info(attachment_id)
        info.rel = str(post.get('_id'))
        attachments.append(info)
          
    comments = post.get('comments')
    if not comments:
      continue
    for comment in comments:
      if comment.has_key('attachments'):
        for i in comment.get('attachments', []):
          if i not in ids:
            ids.add(i)
            info = get_attachment_info(i)
            info.rel = str(post.get('_id'))
            attachments.append(info)
  
  attachments.sort(key=lambda k: k.timestamp, reverse=True)
  return [i for i in attachments if i.name]
  
  
  
# Group Actions --------------------------------------------------------------
def new_group(session_id, name, privacy="closed", about=None):
  """
  Privacy: Open|Closed|Secret
  """
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
    

  info = {'timestamp': utctime(),
          'last_updated': utctime(),
          'members': [user_id],
          'leaders': [user_id],
          'name': name, 
          'privacy': privacy,
          '_id': new_id()}
  if about:
    info['about'] = about.strip()
    
  db.owner.insert(info)
  group_id = info['_id']
  
  key = '%s:groups' % user_id
  cache.delete(key)
  
  key = '%s:group_ids'
  cache.delete(key)
  
  new_feed(session_id, {'action': 'created',
                        'group_id': group_id}, [group_id])
  
  return group_id
  


def update_group_info(session_id, group_id, info):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  if info.has_key('members'):
    info['members'] = [long(i) for i in info.get('members')]
  
  db.owner.update({'leaders': user_id, 
                   '_id': long(group_id)}, {'$set': info})
  return True

def join_group(session_id, group_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  group_info = db.owner.find_one({'_id': long(group_id)})
  if not group_info:
    return False
  
  key = '%s:groups' % user_id
  cache.delete(key)
  
  key = '%s:group_ids' % user_id
  cache.delete(key)
  
  if group_info.get('privacy') == 'open':
    db.owner.update({'_id': group_id}, 
                          {'$addToSet': {'members': user_id}})
    
    for user_id in group_info.get('leaders', []):
      notification_queue.enqueue(new_notification, 
                                 session_id, user_id, 
                                 'new_member', 
                                 ref_id=group_id, 
                                 ref_collection='owner', 
                                 db_name=db_name)
    return True
  
  elif group_info.get('privacy') == 'closed':
    pending_members = group_info.get('pending_members', [])
    if user_id not in pending_members:
      pending_members.append(user_id)
      db.owner.update({'_id': group_id}, 
                      {'$set': {'pending_members': pending_members}})
      
      
      for user_id in group_info.get('leaders', []):
        notification_queue.enqueue(new_notification, 
                                   session_id, user_id, 
                                   'ask_to_join', 
                                   ref_id=group_id, 
                                   ref_collection='owner', 
                                   db_name=db_name)
      
      return None
    
    return False
  
def leave_group(session_id, group_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  group_info = db.owner.find_one({'_id': long(group_id)})
  if not group_info:
    return False
  
  
  key = '%s:groups' % user_id
  cache.delete(key)
  
  key = '%s:group_ids' % user_id
  cache.delete(key)
  
  if group_info.get('privacy') == 'open':
    db.owner.update({'_id': group_id}, {'$pull': {'members': user_id}})
    db.owner.update({'_id': group_id}, {'$pull': {'pending_members': user_id}})
    
    return True
  elif group_info.get('privacy') == 'closed':
    pending_members = group_info.get('pending_members', [])
    if user_id in pending_members:
      pending_members.remove(user_id)
      db.owner.update({'_id': group_id}, 
                            {'$set': {'pending_members': pending_members}})
      return None
    return False
  
def add_member(session_id, group_id, user_id):
  # TODO: datetime user join group
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = long(user_id)
  group_id = long(group_id)
  owner_id = get_user_id(session_id)
  if not owner_id:
    return False
  
  group_info = db.owner.find_one({'_id': long(group_id),
                                  'members': owner_id})
  if not group_info:
    return False
  
  key = '%s:groups' % user_id
  cache.delete(key)
  
  key = '%s:group_ids' % user_id
  cache.delete(key)
  
  is_approved = False
  if user_id in group_info.get('pending_members', []):
    db.owner.update({'_id': group_id},
                    {'$addToSet': {'members': user_id},
                     '$pull': {'pending_members': user_id}})
    is_approved = True
  else:
    db.owner.update({'_id': group_id},
                    {'$addToSet': {'members': user_id}})
  
  new_feed(session_id, {'action': 'added',
                        'user_id': user_id, 
                        'group_id': group_id}, viewers=[group_id])
  

  user = get_user_info(user_id)
  owner = get_user_info(owner_id)
  group = Group(group_info, db_name=db_name)
  
  if user.has_password:
    is_new_user = False
  else:
    is_new_user = True
    
  
  if is_approved:
    new_notification(session_id, user_id, type='approved', 
                     ref_id=group_id, ref_collection='owner', db_name=db_name)
  else:
    new_notification(session_id, user_id, type='add_member', 
                     ref_id=group_id, ref_collection='owner', db_name=db_name)
      
    send_mail_queue.enqueue(send_mail, user.email, 
                            mail_type='invite',
                            is_new_user=is_new_user,
                            user_id=owner.id,
                            username=owner.name,
                            group_id=group.id,
                            group_name=group.name,
                            db_name=db_name)
  
  return True
  
def remove_member(session_id, group_id, user_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = long(user_id)
  group_id = long(group_id)
  owner_id = get_user_id(session_id)
  if not owner_id:
    return False
  group_info = db.owner.find_one({'_id': long(group_id),
                                  'leaders': owner_id})
  if not group_info:
    return False
  
  db.owner.update({'_id': group_id},
                  {'$pull': {'members': user_id}})
  
  if group_info.get('privacy') != 'open':
    db.owner.update({'_id': group_id},
                    {'$pull': {'pending_members': user_id}})
  
  db.owner.update({'_id': group_id},
                  {'$pull': {'leaders': user_id}})
  
  
  key = '%s:groups' % user_id
  cache.delete(key)
  
  key = '%s:group_ids' % user_id
  cache.delete(key)
  
  return True
  
def make_admin(session_id, group_id, user_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = long(user_id)
  
  if str(group_id).isdigit():
    group_id = long(group_id)
  elif group_id == 'public':
    pass
  else:
    return False
  
  owner_id = get_user_id(session_id)
  if not owner_id:
    return False
  
  if group_id == 'public':
    if is_admin(owner_id, group_id):
      db.owner.update({'_id': user_id}, {'$set': {'admin': True}})
      
      key = '%s:info' % user_id
      cache.delete(key)
      
      new_notification(session_id, user_id, 'make_admin', 
                       ref_id=group_id, 
                       ref_collection='owner', db_name=db_name)
      
      return True
    else:
      return False
  
  group_info = db.owner.find_one({'_id': long(group_id),
                                  'leaders': owner_id})
  if not group_info:
    return False
  
  db.owner.update({'_id': group_id},
                  {'$addToSet': {'leaders': user_id}})
      
  new_notification(session_id, user_id, 'make_admin', 
                   ref_id=group_id, 
                   ref_collection='owner',
                   db_name=db_name)
  
  if user_id not in group_info.get('members', []):
    db.owner.update({'_id': group_id},
                    {'$addToSet': {'members': user_id}})
    
  
  #TODO: send notification
  
  key = '%s:groups' % user_id
  cache.delete(key)
  
  key = '%s:group_ids' % user_id
  cache.delete(key)
  
  return True
  
def remove_as_admin(session_id, group_id, user_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = long(user_id)
  
  if str(group_id).isdigit():
    group_id = long(group_id)
  elif group_id == 'public':
    pass
  else:
    return False
  
  owner_id = get_user_id(session_id)
  if not owner_id:
    return False
  
  if group_id == 'public':
    if is_admin(owner_id, group_id):
      db.owner.update({'_id': user_id}, {'$unset': {'admin': True}})
      
      key = '%s:info' % user_id
      cache.delete(key)
      
      return True
    
    else:
      return False
    
  
  group_info = db.owner.find_one({'_id': long(group_id),
                                  'leaders': owner_id})
  if not group_info:
    return False
  
  db.owner.update({'_id': group_id},
                  {'$pull': {'leaders': user_id}})
  
  key = '%s:groups' % user_id
  cache.delete(key)
  
  key = '%s:group_ids' % user_id
  cache.delete(key)
  
  return True
    
def add_to_contacts(session_id, user_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  uid = get_user_id(session_id)
  if not uid:
    return False
  db.owner.update({'_id': uid},
                  {'$addToSet': {'contacts': long(user_id)}})
  
  # TODO: send notification
  new_notification(session_id, user_id, 'add_contact')
  
  key = '%s:info' % uid
  cache.delete(key)
  
  key = '%s:friends_suggestion' % uid
  cache.delete(key)
  
  return True

def remove_from_contacts(session_id, user_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  uid = get_user_id(session_id)
  if not uid:
    return False
  db.owner.update({'_id': uid},
                  {'$pull': {'contacts': long(user_id)}})
  
  # TODO: send notification
  
  
  key = '%s:info' % uid
  cache.delete(key)
  
  key = '%s:friends_suggestion' % uid
  cache.delete(key)
  
  return True

def follow(session_id, user_id):   
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  uid = get_user_id(session_id)
  if not uid:
    return False
  db.owner.update({'_id': user_id},
                  {'$addToSet': {'followers': uid}})
  
  # send notification
  new_notification(session_id, user_id, 'follow', id)
  
  return True

def unfollow(session_id, user_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  _id = get_user_id(session_id)
  if not _id:
    return False
  db.owner.update({'_id': user_id},
                  {'$pull': {'followers': _id}})
  return True
  
  
  
def get_group_id(service_key):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = db.owner.find_one(service_key, {'_id': True})
  if info:
    return info['_id']
  
def get_new_webhook_key(session_id, group_id, service_name):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False

  key = uuid4().hex
  db.owner.update({'_id': long(group_id), 'leaders': user_id},
                  {'$set': {'%s_key' % service_name: key}})
  return key

def new_hook_post(service_name, key, message):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  query = {'%s_key' % service_name: key}
  group_id = get_group_id(query)
  if service_name == 'gitlab':
    email = 'gitlab@gitlabhq.com'
    user = db.owner.find_one({'email': email}, 
                             {'session_id': True})
    if not user:
      session_id = sign_up(email='gitlab@gitlabhq.com', 
                           password='gitlab', name='Gitlab')
    else:
      session_id = user['session_id']
    return new_feed(session_id, str(message), viewers=[group_id])
  elif service_name == 'github':
    email = 'github@github.com'
    user = db.owner.find_one({'email': email}, 
                             {'session_id': True})
    if not user:
      session_id = sign_up(email='github@github.com', 
                           password='github', name='GitHub')
    else:
      session_id = user['session_id']
    return new_feed(session_id, str(message), viewers=[group_id])


def get_group_ids(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not user_id or not str(user_id).isdigit():
    return []
  
  key = '%s:group_ids' % user_id
  ids = cache.get(key)
  if not ids:
    groups = db.owner.find({"members": long(user_id)}, {'_id': True})
    ids = [i.get('_id') for i in groups]
    cache.set(key, ids)
  return ids


def get_following_users(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if not user_id:
    return []
  users = db.owner.find({'followers': long(user_id)}, {'_id': True})
  return [i['_id'] for i in users]
  

def get_groups_count(user_id, db_name=None):
  if not user_id:
    return 0
  
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  return len(get_group_ids(user_id, db_name=db_name))
  
  
  
@line_profile
def get_groups(session_id, limit=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return []
  
  key = '%s:groups' % user_id
  groups = cache.get(key)
  if groups is None:
    groups = db.owner.find({"members": user_id}).sort('last_updated', -1)
    groups = [Group(i, db_name=db_name) for i in groups]
    cache.set(key, groups)

  if not groups:
    return []
  elif limit:
    return groups[:limit]
  else:
    return groups
  

def get_open_groups(user_id=None, limit=5):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  if user_id:
    groups = db.owner.find({'members': {'$in': [user_id]},
                            'privacy': 'open'})\
                     .sort('last_updated', -1).limit(limit)
  else:
    groups = db.owner.find({'privacy': 'open'})\
                     .sort('last_updated', -1).limit(limit)
  return [Group(i, db_name=db_name) for i in groups]


def get_featured_groups(session_id, limit=5):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  
  groups = db.owner.find({'privacy': 'open'})\
                   .sort('last_updated', -1).limit(limit*2)
  
  featured_groups = []
  for group in groups:
    if user_id not in group.get('members'):
      featured_groups.append(Group(group, db_name=db_name))
  
  return featured_groups
  
def get_first_user_id(db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  key = 'first_user_id:%s' % db_name
  user_id = cache.get(key)
  if user_id:
    return user_id
  
  user = db.owner.find({'password': {'$ne': None},
                        'timestamp': {'$ne': None}}, 
                       {'_id': True}).sort('timestamp', 1).limit(1)
  user = list(user)
  if user:
    user_id = user[0]['_id']
    cache.set(key, user_id)
    
    db.owner.update({'_id': user_id}, {'$set': {'admin': True}})
    
    key = '%s:info' % user_id
    cache.delete(key)
    
    return user_id

def is_admin(user_id, group_id=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  
  if str(group_id).isdigit():
    group = db.owner.find_one({'_id': long(group_id), 
                               'leaders': long(user_id)})
    
    if group:
      return True
    else:
      return False
  else:
    user = get_user_info(user_id)
    if user.is_admin():
      return True
    
    if user_id == get_first_user_id():
      return True
    else:
      return False

def get_group_member_ids(group_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if str(group_id).isdigit():
    group = db.owner.find_one({'_id': long(group_id)}, {'members': True,
                                                        'leaders': True})
    ids = set()
    for i in group.get('members', []):
      ids.add(i)
    for i in group.get('leaders', []):
      ids.add(i)
    return ids
  else:
    group_id = 'public'
    users = get_all_users()
    return [user.id for user in users]


def highlight(session_id, group_id, note_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  db.owner.update({'_id': long(group_id), 'leaders': user_id},
                        {'$addToSet': {'highlights': long(note_id)}})
  return True


def unhighlight(session_id, group_id, note_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  db.owner.update({'_id': long(group_id), 'leaders': user_id},
                        {'$pull': {'highlights': long(note_id)}})
  return True
  


def is_public(group_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = db.owner.find_one({"_id": long(group_id)})
  return True if info and info.get('privacy') == 'open' else False


def get_group_info(session_id, group_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if group_id == 'public':
    leaders = get_network_admin_ids(db_name)
      
    info = {'name': 'Public',
            'leaders': leaders,
            'members': get_group_member_ids(group_id, db_name=db_name),
            '_id': 'public'}
    return Group(info, db_name=db_name)
  
  if not str(group_id).isdigit():
    return Group({})
  else:
    group_id = long(group_id)
    
  user_id = get_user_id(session_id, db_name=db_name)
  info = db.owner.find_one({"_id": group_id})
  if info and info.get('privacy') in ['open', 'closed'] or user_id in info['members']:
    if not info.has_key('recently_viewed'): # preinitialize recently_viewed arrays with nulls
      db.owner.update({'_id': group_id},
                      {'$set': 
                       {'recently_viewed': [None for __ in xrange(0, 250)]}})
    return Group(info, db_name=db_name)
  else:
    return Group({}) 

def add_to_recently_viewed_list(session_id, group_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  ts = utctime()
  db.owner.update({'_id': group_id},
                        {'$push': {'recently_viewed': {'user_id': user_id,
                                                       'timestamp': ts}}})
  db.owner.update({'_id': group_id},
                        {'$pop': {'recently_viewed': -1}})
  return True


def regex_search(query):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  raw_query = query
  query = query.strip().replace(' ', '.*') + '.*'
  query = re.compile(query, re.IGNORECASE)
  feeds = db.stream.find({'message': query})\
                              .sort('last_updated', -1).limit(10)
  docs = db.stream.find({'_content': query})\
                          .sort('last_updated', -1).limit(10)
  items = list(feeds)
  items.extend(docs)
  items = [Result(i, raw_query) for i in items]
  return items

def add_index(_id, content, viewers, type_='post', db_name=None):
  if isinstance(content, dict): # system messages
    return False 
  
  if not viewers:
    return False
  
  if not _id:
    return False
  
  if not db_name:
    db_name = get_database_name()
  
  viewers = ' '.join([str(i) for i in set(viewers)])
  info = {'content': content,
          'viewers': viewers,
          'comments': '',
          'ts': utctime(),
          'type': type_,
          'id': str(_id)}
  INDEX.index(db_name, 'doc', info)
  INDEX.refresh(db_name)
  return True

def update_viewers(_id, viewers, db_name=None):
  if not db_name:
    db_name = get_database_name()
    
  query = 'id:%s' % _id
  result = INDEX.search(query, index=db_name)
  hits = result.get('hits').get('hits')   # pylint: disable-msg=E1103
  if hits:
    index_id = hits[0].get('_id')
    viewers = ' '.join([str(i) for i in set(viewers)])
    
    info = {'content': hits[0].get('_source').get('content'),
            'comments': hits[0].get('_source').get('comments'),
            'viewers': viewers,
            'ts': hits[0].get('_source').get('ts', utctime()),
            'type': hits[0].get('_source').get('type'),
            'id': str(_id)}
    
    for __ in xrange(5):
      try:
        INDEX.index(db_name, 'doc', info, index_id)
        INDEX.refresh(db_name)
        return True
      except CannotSendRequest:
        continue
  

def update_index(_id, content, viewers, is_comment=False, db_name=None):
  if not db_name:
    db_name = get_database_name()
  
  if viewers is None:
    viewers = []
  if isinstance(viewers, str) or isinstance(viewers, unicode):
    viewers = [viewers]
  query = 'id:%s' % _id
  result = INDEX.search(query, index=db_name)
  hits = result.get('hits').get('hits')   # pylint: disable-msg=E1103
  if hits:
    index_id = hits[0].get('_id')
    viewers = ' '.join([str(i) for i in set(viewers)])
    if is_comment:
      comment = '%s %s' % (hits[0].get('_source').get('comments', ''), content)
      info = {'content': hits[0].get('_source').get('content'),
              'comments': comment,
              'viewers': viewers,
              'ts': utctime(),
              'type': hits[0].get('_source').get('type'),
              'id': str(_id)}
    else:
      info = {'content': content,
              'comments': hits[0].get('_source').get('comments', ''),
              'viewers': viewers,
              'ts': utctime(),
              'type': hits[0].get('_source').get('type'),
              'id': str(_id)}
    for __ in xrange(5):
      try:
        INDEX.index(db_name, 'doc', info, index_id)
        INDEX.refresh(db_name)
        return True
      except CannotSendRequest:
        continue
  return False
  
def people_search(query, group_id=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  query = query.strip().lower()
  
  if '@' in query:
    users = db.owner.find({'email': re.compile(query, re.IGNORECASE)})\
                    .limit(50)
  else:
    users = db.owner.find({'name': re.compile(query, re.IGNORECASE)})\
                    .limit(50)
    users = list(users)
    user_ids = [u['_id'] for u in users]
    if len(list(user_ids)) < 5:
      _users = db.owner.find({'email': re.compile(query, re.IGNORECASE)})\
                       .limit(50)
      for _user in _users:
        if _user['_id'] not in user_ids:
          users.append(_user)
          user_ids.append(_user['_id'])
  return [User(i, db_name=db_name) for i in users if i.get('email')]


def search(session_id, query, type=None, ref_user_id=None, page=1):
  db_name = get_database_name()
  
  hashtag_id = None
  if query.startswith('#'):
    hashtag_id = query.lstrip('#').lower()
    query = '\#\[\%s\]\(hashtag\:%s\)' % (query, hashtag_id)
  
  user_id = get_user_id(session_id)
  if not user_id:
    user_id = 'public'
  
  if ref_user_id:
    viewers = '(viewers:%s) AND (viewers:%s)' % (user_id, ref_user_id)
  else:
    if user_id != 'public':
      group_ids = get_group_ids(user_id)
      group_ids.append(user_id)
      viewers = ['viewers:%s' % i for i in group_ids]
      viewers = ' OR '.join(viewers)
      viewers += ' OR viewers:public'
    else:
      viewers = 'viewers:public'
  
  
  if hashtag_id:
    query = '(%s) AND (content:%s OR comments:%s)' % (viewers, query, query)
  else:
    query = '(%s) AND (content:*%s* OR comments:*%s*)' % (viewers, query, query)
    
  if type:
    query += ' AND type:%s' % type 
  
  print query
  query_dsl =  {}

  query_dsl['query'] = {"query_string": {"query": query}}
  query_dsl['from'] = (page - 1) * 5
  query_dsl['size'] = 5
  query_dsl['sort'] = [{'ts': {'order': 'desc'}}, 
                       {'id': {'order': 'desc'}}, 
                       "_score"]
  query_dsl["facets"] = {"counters": {"terms": {"field" : "type"}}}
      
  try:
    result = INDEX.search(query=query_dsl, index=db_name)
  except ElasticHttpNotFoundError:
    return None
  

  if result and result.has_key('hits'): # pylint: disable-msg=E1103
    hits = result['hits'].get('hits')
    results = {}
    results['counters'] = result['facets']['counters']['terms']
    results['hits'] = []
    for hit in hits:
      info = get_record(hit.get('_source').get('id'))
      if info and not info.has_key('is_removed'):
#        results.append(ESResult(info, query))
        results['hits'].append(Feed(info, db_name=db_name))
      
    results['hits'].sort(key=lambda k: k.last_updated, reverse=True)
    return results
  return None
    
    
def _jupo_stats():
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  users = db.owner.find({'password': {'$ne': None}}).count()
  groups = db.owner.find({'privacy': {'$ne': None}}).count()
  emails = db.owner.find().count() - users - groups
  subscribers = db.waiting_list.find().count()
  return {'users': users,
          'groups': groups,
          'emails': emails,
          'subscribers': subscribers}
  
  
def get_google_spelling_suggestion(query):
  db = DATABASE['global']
  
  url = 'http://www.google.com/search?q=%s&start=0&hl=en' % quote(str(query))
  html = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; U; Linux x86_64; en-US) AppleWebKit/534.16 (KHTML, like Gecko) Ubuntu/10.10 Chromium/10.0.648.133 Chrome/10.0.648.133 Safari/534.16',
                                    'Referer': 'http://www.google.com/'}).content
  suggestions = re.compile('class="spell".*?>(.*?)</a>').findall(html)
  if suggestions:
    text = suggestions[0]
    suggestion = re.findall('<i>(.*?)</i>', text)[0]
    if suggestion:
      db.spelling_suggestion.insert({'keyword': query.lower().strip(), 
                                     'suggestion': suggestion})
      return suggestion

def get_spelling_suggestion(keyword):
  db = DATABASE['global']
  
  keyword = keyword.lower().strip()
  info = db.spelling_suggestion.find_one({'keyword': keyword})
  if info:
    suggestion = info.get('suggestion')
    return {'text': suggestion,
            'html': '<b><i>%s</i></b>' % suggestion}
  else:
    crawler_queue.enqueue(get_google_spelling_suggestion, keyword)

#===============================================================================
# Push
#===============================================================================
def is_valid_channel_id(session_id, channel_id):
  if session_id == channel_id:
    return False
  
  db_name = get_database_name()
  key = hashlib.md5('%s|%s' % (db_name, session_id)).hexdigest()
  if key == channel_id:
    return True
  else:
    return False
  

def get_channel_id(user_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
    
  if str(user_id).isdigit():
    session_id = get_session_id(user_id, db_name=db_name)
  else:
    session_id = user_id
    
  return hashlib.md5('%s|%s' % (db_name, session_id)).hexdigest()
    

def publish(user_id, event_type, info=None, db_name=None):    
  if event_type == 'friends-online':
    template = app.CURRENT_APP.jinja_env.get_template('friends_online.html')
  
    user_id = long(user_id)
    owner = get_user_info(user_id, db_name=db_name)
    owner.status = info
    
    users = DATABASE[db_name].owner.find({'contacts': user_id}, {'_id': True})
    user_ids = list(set([i.get('_id') for i in users]))
    if user_id in user_ids:
      user_ids.remove(user_id)
        
    item = {'type': event_type,
            'user': {'id': str(owner.id),
                     'name': owner.name,
                     'avatar': owner.avatar,
                     'status': info}}
        
    for user_id in user_ids:
      channel_id = get_channel_id(user_id, db_name=db_name)
      user = get_user_info(user_id, db_name=db_name)
      item['info'] = template.render(owner=user,
                                     friends_online=[owner])
      data = dumps(item)
      PUBSUB.publish(channel_id, data)
        
  elif event_type == 'read-receipts':
    owner = get_user_info(user_id, db_name=db_name)
    template = app.CURRENT_APP.jinja_env.get_template('read_receipts.html')
    
    read_receipts = []
    last_updated = info.get('last_updated')
    for i in info.get('read_receipts'):
      if i.get('timestamp') > last_updated:
        read_receipts.append({'user': get_user_info(i['user_id'], db_name=db_name),
                              'timestamp': i['timestamp']})
    read_receipts.sort(key=lambda k: k.get('timestamp'), reverse=True)
    
    quick_stats = '''
      <i class="receipt-icon"></i>
      <span class="read-receipts-count">%s</span>''' % len(read_receipts)
    
    text = template.render(owner=owner, read_receipts=read_receipts)
    
    channel_id = get_channel_id(user_id, db_name=db_name)
    PUBSUB.publish(channel_id, dumps({'type': event_type,
                                      'info': {'post_id': str(info.get('_id')), 
                                               'quick_stats': quick_stats,
                                               'owner': str(user_id),
                                               'viewers': [str(i) for i in info.get('viewers', [])], 
                                               'text': text}}))
      
  elif event_type == 'like-comment':
    likes_count = len(info['likes'])
    
    if likes_count == 1:
      msg = '%s likes this.' % (info['likes'][0].name)
    else:
      msg = '%s like this.' % (', '.join([user.name for user in info['likes']]))
      
    
    channel_id = get_channel_id(user_id, db_name=db_name)
    PUBSUB.publish(channel_id, dumps({'type': event_type,
                                      'info': {'comment_id': str(info['_id']),
                                               'likes_count': likes_count,
                                               'text': msg}}))
                                         
    
  elif event_type == 'likes':
    owner = get_user_info(user_id, db_name=db_name)
    likes = info['likes']
    
    quick_stats = '''
      <i class="like-icon"></i>
      <span class="likes-count">%s</span>''' % len(likes)
    
    template = app.CURRENT_APP.jinja_env.get_template('likes.html')
    html = template.render(owner=owner, likes=likes, item={'id': info['_id']})
    
    channel_id = get_channel_id(user_id, db_name=db_name)
    PUBSUB.publish(channel_id, dumps({'type': event_type,
                                      'info': {'post_id': str(info.get('_id')), 
                                               'quick_stats': quick_stats,
                                               'html': html}}))
    
  
  elif 'unread-feeds' in event_type:
    template = app.CURRENT_APP.jinja_env.get_template('feed.html')
    feed = Feed(info, db_name=db_name)
    
    if '|' in event_type:
      group_id = event_type.split('|')[0]
      if is_group(group_id):
        session_id = get_session_id(user_id, db_name=db_name)
        members = get_group_info(session_id, 
                                 int(group_id), 
                                 db_name=db_name).members
        members = set([str(user.id) for user in members])
        for user_id in members:
          owner = get_user_info(user_id, db_name=db_name)
          # TODO: sử dụng _render ở dưới đến tận dụng cache?
          html_group = template.render(feed=feed, 
                                       owner=owner, 
                                       view='group')
          html_news_feed = template.render(feed=feed, 
                                           owner=owner, 
                                           view='news_feed')
          
          channel_id = get_channel_id(user_id, db_name=db_name)
          PUBSUB.publish(channel_id, 
                         dumps({'type': 'unread-feeds', 
                                'viewers': [str(i) for i in feed.viewers], 
                                'info': html_news_feed}))
          PUBSUB.publish(channel_id, 
                         dumps({'type': event_type, 
                                'viewers': [str(i) for i in feed.viewers], 
                                'info': html_group}))
    else:
      owner = get_user_info(user_id, db_name=db_name)
      html = template.render(feed=feed, 
                             owner=owner, 
                             view='news_feed')
      
      channel_id = get_channel_id(user_id, db_name=db_name)
      PUBSUB.publish(channel_id, 
                     dumps({'type': 'unread-feeds', 'info': html}))
      
  elif event_type == 'new-message':
    html = info.replace('\n', '')
    channel_id = get_channel_id(user_id, db_name=db_name)
    PUBSUB.publish(channel_id, 
                   dumps({'type': event_type, 
                          'info': {'html': html}}))  
      
  else: # unread-notifications/typing-status/new-message
    channel_id = get_channel_id(user_id, db_name=db_name)
    PUBSUB.publish(channel_id, 
                   dumps({'type': event_type, 'info': info}))  
    
  return True



def clear_html_cache(post_id):
  cache.clear(namespace=post_id)
  return True
    
    

def like(session_id, item_id, post_id=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  db.like.insert({'user_id': user_id,
                  'item_id': item_id,
                  'timestamp': utctime()})
  
  key = '%s:liked_user_ids' % item_id
  cache.delete(key)  
    
  record = get_record(post_id, db_name=db_name)
  if not record:
    return False
  
  viewers = record.get('viewers', [])
  viewers.append(user_id)
  
  if post_id == item_id:  # like post
    
    likes = [get_user_info(i) for i in  get_liked_user_ids(post_id)]
    record['likes'] = likes
    for uid in viewers:
      push_queue.enqueue(publish, uid, 'likes', record, db_name=db_name)
    
    if record['owner'] != user_id:
      notification_queue.enqueue(new_notification, 
                                 session_id, 
                                 record['owner'], 
                                 'like', post_id, db_name=db_name)
  else: # comment like
    for comment in record['comments']:
      if comment['_id'] == item_id:
        if user_id != comment['owner']:
          notification_queue.enqueue(new_notification, 
                                     session_id, 
                                     comment['owner'], 
                                     'like', post_id, 
                                     comment['_id'], db_name=db_name)
        break
    
    likes = [get_user_info(i) for i in  get_liked_user_ids(item_id)]
    comment['likes'] = likes
    for uid in viewers:
      push_queue.enqueue(publish, uid, 'like-comment', comment, db_name=db_name)
        
    
  clear_html_cache(post_id)
  
  
  return True

def unlike(session_id, item_id, post_id=None):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  db.like.remove({'user_id': user_id, 'item_id': item_id})
  
  key = '%s:liked_user_ids' % item_id
  cache.delete(key)
  
  record = get_record(post_id, db_name=db_name)
  if not record:
    return False
  
  viewers = record.get('viewers', [])
  viewers.append(user_id)
  
  if post_id == item_id:
    likes = [get_user_info(i) for i in  get_liked_user_ids(post_id)]
    record['likes'] = likes
    for uid in viewers:
      push_queue.enqueue(publish, uid, 'likes', record, db_name=db_name)
  else:
    
    for comment in record['comments']:
      if comment['_id'] == item_id:
        break
        
    likes = [get_user_info(i) for i in  get_liked_user_ids(item_id)]
    comment['likes'] = likes
    for uid in viewers:
      push_queue.enqueue(publish, uid, 'like-comment', comment, db_name=db_name)  
      
  clear_html_cache(post_id)
    
  return True

def is_liked_item(user_id, item_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = db.like.find_one({'user_id': long(user_id),
                           'item_id': long(item_id)})
  if info:
    return True
  else:
    return False
  
def get_liked_user_ids(item_id, db_name=None):
  key = '%s:liked_user_ids' % item_id
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  records = db.like.find({'item_id': long(item_id)}).sort('timestamp', -1)
  user_ids = [i['user_id'] for i in records]
  cache.set(key, user_ids)
  return user_ids
  
  


def ensure_index(db_name=None):
  db = DATABASE[db_name]
  
  db.owner.ensure_index('session_id', background=True)
  db.owner.ensure_index('email', background=True)
  db.owner.ensure_index('name', background=True)
  db.owner.ensure_index('members', background=True)
  db.owner.ensure_index('password', background=True)
  
  db.notification.ensure_index('receiver', background=True)
  db.notification.ensure_index('is_unread', background=True)
  db.notification.ensure_index('timestamp', background=True)
  
  db.stream.ensure_index('viewers', background=True)
  db.stream.ensure_index('last_updated', background=True)
  db.stream.ensure_index('archived_by', background=True)
  db.stream.ensure_index('attachments', background=True)
  db.stream.ensure_index('comments.attachments', background=True)
  db.stream.ensure_index('version', background=True)
  db.stream.ensure_index('history.attachment_id', background=True)
  db.stream.ensure_index('is_removed', background=True)
  
  db.reminder.ensure_index('owner', background=True)
  db.reminder.ensure_index('checked', background=True)
  
  db.message.ensure_index('from', background=True)
  db.message.ensure_index('to', background=True)
  db.message.ensure_index('topic', background=True)
  db.message.ensure_index('owner', background=True)
  db.message.ensure_index('user_id', background=True)
  db.message.ensure_index('topic_id', background=True)
  db.message.ensure_index('members', background=True)
  
  db.like.ensure_index('item_id', background=True)
  db.like.ensure_index('user_id', background=True)
  
  db.status.ensure_index('user_id', background=True)
  db['s3'].ensure_index('name', background=True)
  
  db.url.ensure_index('url', background=True)
  return True


def add_db_name(email, db_name):
  if not email:
    return False
  email = email.lower().strip()
  db_name = db_name.lower().strip()
  DATABASE['global']['user'].update({'email': email},
                                    {'$addToSet': {'db_names': db_name}}, 
                                    upsert=True)
  return True


def get_db_names(email):
  if email:
    email = email.lower().strip()
    info = DATABASE['global']['user'].find_one({'email': email})
    if info:
      return info.get('db_names')
  return []


def new_network(db_name, organization_name, description=None):
  if is_exists(db_name=db_name):
    return False
  
  info = {'domain': db_name.replace('_', '.'),
          'name': organization_name,
          'description': description,
          'timestamp': utctime()}
  DATABASE[db_name].info.insert(info)
  key = 'db_names'
  cache.delete(key)
  
  primary_db_name = settings.PRIMARY_DOMAIN.replace('.', '_')
  for user_id in get_network_admin_ids(primary_db_name):
    notification_queue.enqueue(new_notification, 
                               None, user_id, 
                               'new_network', 
                               ref_id=db_name, 
                               ref_collection='info', 
                               db_name=primary_db_name)
  
  ensure_index(db_name)
  return True


def get_network_admin_ids(db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  users = db.owner.find({'admin': True}, {'_id': True})
  users = list(users)
  if users:
    return [i['_id'] for i in users]
  return [get_first_user_id(db_name)]

@line_profile
def get_network_info(db_name):
  key = '%s:info' % db_name
  info = cache.get(key)
  if info is not None:
    return info 
  
  if db_name == settings.PRIMARY_DOMAIN.replace('.', '_'):
    info = {'name': 'Jupo', 'timestamp': 0}
  else:
    info = DATABASE[db_name].info.find_one()
    
  cache.set(key, info)
  return info

@line_profile
def get_networks(user_id, user_email=None):
#   key = '%s:networks' % user_id
#   out = cache.get(key)
#   if out is not None:
#     return out
  
  
  def sortkeypicker(keynames):
    negate = set()
    for i, k in enumerate(keynames):
      if k[:1] == '-':
        keynames[i] = k[1:]
        negate.add(k[1:])
        
    def getit(adict):
      composite = [adict[k] for k in keynames]
      for i, (k, v) in enumerate(zip(keynames, composite)):
        if k in negate:
          composite[i] = -v
      return composite
    return getit
  
  if user_email:
    email = user_email
  else:
    email = get_email_addresses(user_id)
  db_names = get_db_names(email)
  networks_list = []

  for db_name in db_names:
    info = get_network_info(db_name)
    if info:
      user_id = get_user_id(email=user_email, db_name=db_name)
      info['unread_notifications'] = get_unread_notifications_count(user_id, db_name=db_name)
      info['domain'] = db_name.replace('_', '.')
      info['url'] = 'http://%s/' % info['domain']
      
      networks_list.append(info)
    
    
  out = sorted(networks_list, 
               key=sortkeypicker(['-unread_notifications', 
                                  'name', '-timestamp']))
#   cache.set(key, out)
  return out

PRIMARY_IP = socket.gethostbyname(settings.PRIMARY_DOMAIN)
def domain_is_ok(domain_name):
  try:
    return PRIMARY_IP in socket.gethostbyaddr(domain_name)[-1]
  except socket.gaierror:
    return False
 

def new_topic(owner_id, user_ids, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = {'_id': new_id(),
          'owner': owner_id,
          'members': user_ids,
          'ts': utctime()}
  db.message.insert(info)
  return info['_id']

def archive_topic(session_id, topic_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  
  key = '%s:%s:unread_messages' % (db_name, user_id)
  cache.delete(key)
  
  key = '%s:%s:messages' % (db_name, user_id)
  cache.delete(key)
  
  db.message.update({'_id': long(topic_id)}, 
                    {'$addToSet': {'archived_by': user_id},
                     '$set': {'ts': utctime()}})
  return True

def unarchive_topic(session_id, topic_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  
  key = '%s:%s:unread_messages' % (db_name, user_id)
  cache.delete(key)
  
  key = '%s:%s:messages' % (db_name, user_id)
  cache.delete(key)
  
  db.message.update({'_id': long(topic_id)}, 
                    {'$pull': {'archived_by': user_id},
                     '$set': {'ts': utctime()}})
  return True


def leave_topic(session_id, topic_id):
  db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = get_user_id(session_id)
  user = get_user_info(user_id)
  
  message = '@[%s](user:%s) left the conversation.' % (user.name, user.id)
  new_message(session_id, message, 
              topic_id=topic_id, is_auto_generated=True)
  
  db.message.update({'_id': long(topic_id)}, 
                    {'$pull': {'members': user_id}})
  return True
  


def update_topic(session_id, topic_id, name, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  name = name.strip()
  
  user_id = get_user_id(session_id)
  if not user_id:
    return False
  
  db.message.update({'_id': long(topic_id)}, {'$set': {'name': name.strip()}})
  
  owner = get_user_info(user_id)
  message = '@[%s](user:%s) set topic to "%s"' % (owner.name, owner.id, name)
  
  new_message(session_id, message, topic_id=topic_id, 
              is_auto_generated=True, db_name=db_name)
  
  return True


def get_topic_ids(user_id, archived=False, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  user_id = long(user_id)
  if archived:
    records = db.message.find({'members': user_id, 
                               'archived_by': user_id})
  else:
    records = db.message.find({'members': user_id, 
                               'archived_by': {'$nin': [user_id]}})
  return [i['_id'] for i in records]
    
def get_topic_info(topic_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  info = db.message.find_one({'_id': int(topic_id), 
                              'members': {'$ne': None}})
  return Topic(info)

def add_topic_members(topic_id, members, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  db.message.update({'_id': int(topic_id)},
                    {'$addToSet': {'members': {"$each": members}}})
  return True
  

def strip_mentions(text):
  out = text
  for i in re.findall('(@\[.*?\))', text):
    out = out.replace(i, '')
  return out
  

def new_message(session_id, message, user_id=None, topic_id=None, 
                is_codeblock=False, is_auto_generated=False, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  owner_id = get_user_id(session_id, db_name=db_name)
  if not owner_id:
    return False
  
  if user_id and not str(user_id).isdigit():
    return False

  if user_id:
    user_id = int(user_id)
  
  if is_auto_generated:
    mentions = []
  else:
    mentions = get_mentions(str(message))
    mentions = [i for i in mentions \
                if i['id'] != owner_id and i['id'] != user_id]
  
  return_empty_html = False
  if user_id and mentions and topic_id is None:
    members = [user_id, owner_id]
    members.extend([int(i.get('id')) for i in mentions])
    topic_id = new_topic(owner_id, members, db_name=db_name)
    
    msg = '@[%s](user:%s) created @[a group conversation](topic:%s)'\
        % (get_user_info(owner_id).name, owner_id, topic_id)
    new_message(session_id, msg, user_id=user_id, 
                is_auto_generated=True, db_name=db_name)
    
    msg = '@[%s](user:%s) added %s to this conversation' \
        % (get_user_info(owner_id).name, owner_id, 
           ', '.join(['@[%s](user:%s)' % (i['name'], i['id']) for i in mentions]))
    
    if ''.join(e for e in strip_mentions(message) if e.isalnum()):
      new_message(session_id, msg, user_id, topic_id, 
                  is_auto_generated=True, db_name=db_name)
    
    else:
      message = msg
      is_auto_generated = True
      
    info = {'_id': new_id(),
            'topic': topic_id,
            'from': owner_id,
            'msg': message,
            'ts': utctime()}
    
    return_empty_html = True
    
  
  elif topic_id:
    topic = get_topic_info(topic_id, db_name=db_name)
    if owner_id not in topic.member_ids:
      return False
    
    db.message.update({'_id': int(topic_id)}, 
                      {'$unset': {'archived_by': 1}})
    
    
    if mentions:
      mentioned = [int(i.get('id')) for i in mentions]
      new_members = [i for i in mentioned if i not in topic.member_ids]
      if new_members:
        add_topic_members(topic_id, new_members, 
                          db_name=db_name)
        
        msg = '@[%s](user:%s) added %s to this conversation' \
            % (get_user_info(owner_id).name, owner_id, 
               ', '.join(['@[%s](user:%s)' \
                              % (i['name'], i['id']) for i in mentions]))
   
        # the message only contains mentions or anything else?
        if ''.join(e for e in strip_mentions(message) if e.isalnum()):
          new_message(session_id, msg, 
                      user_id=user_id, topic_id=topic_id, 
                      is_auto_generated=True, db_name=db_name)
        else:
          message = msg
          is_auto_generated = True
                    
      
    info = {'_id': new_id(),
            'topic': topic_id,
            'from': owner_id,
            'msg': message,
            'ts': utctime()}
  
  else:
    info = {'_id': new_id(),
            'from': owner_id,
            'to': user_id,
            'msg': message,
            'ts': utctime()}
    
  if is_auto_generated:
    info['auto_generated'] = True
    
  if is_codeblock:
    info['codeblock'] = True
  
  msg_id = db.message.insert(info)
  info['_id'] = msg_id
  
  
  key = '%s:%s:messages' % (db_name, owner_id)
  cache.delete(key)
  
  if user_id:
    update_last_viewed(owner_id, user_id=user_id, db_name=db_name)
    key = '%s:%s:unread_messages' % (db_name, user_id)
    cache.delete(key)
  else:
    update_last_viewed(owner_id, topic_id=topic_id, db_name=db_name)
    key = '%s:%s:unread_messages' % (db_name, topic_id)
    cache.delete(key)
  
  utcoffset = get_utcoffset(owner_id, db_name=db_name)
  msg = Message(info, utcoffset=utcoffset, db_name=db_name)
  
  template = app.CURRENT_APP.jinja_env.get_template('message.html')
  html = template.render(message=msg).replace('\n', '')
  if topic_id:
    topic = get_topic_info(topic_id, db_name=db_name)
    user_ids = topic.member_ids
    for uid in user_ids:
      push_queue.enqueue(publish, uid, 'new-message', 
                         info=html, db_name=db_name)
  else:
    push_queue.enqueue(publish, user_id, 'new-message', 
                       info=html, db_name=db_name)
    push_queue.enqueue(publish, owner_id, 'new-message', 
                       info=html, db_name=db_name)
    
  if return_empty_html:
    return ''
  else:
    return html

@line_profile
def get_messages(session_id, archived=False, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  owner_id = get_user_id(session_id, db_name=db_name)
  if not owner_id:
    return False
  
  key = '%s:%s:messages' % (db_name, owner_id)
  if archived is False:
    messages = cache.get(key)
    if messages is not None:
      return messages 
  
  messages = []
  
  if archived is False:
    users = db.message.find({'owner': owner_id,
                             'user_id': {'$ne': None}})
    for user in users:
      user_id = user.get('user_id')
      msg = db.message.find({'$or': [{'from': user_id, 'to': owner_id},
                                     {'from': owner_id, 'to': user_id}],
                             'topic': None})\
                      .sort('ts', -1)\
                      .limit(1)
      msg = list(msg)
      if msg:
        msg = msg[0]
        
        if msg.get('to') == owner_id:
          last_viewed = get_last_viewed(owner_id, user_id, db_name=db_name)
          
          if last_viewed < msg.get('ts'):
            msg['is_unread'] = True
            
        messages.append(msg)
        
  topic_ids = get_topic_ids(owner_id, archived=archived, db_name=db_name)
  for topic_id in topic_ids:
    msg = db.message.find({'topic': topic_id})\
                    .sort('ts', -1)\
                    .limit(1)
    msg = list(msg)
    if msg:
      msg = msg[0]
      messages.append(msg)
  
  messages.sort(key=lambda k: k.get('ts'), reverse=1)
  
  utcoffset = get_utcoffset(owner_id, db_name=db_name)
  
  messages = [Message(i, utcoffset=utcoffset, db_name=db_name) for i in messages]
  
  if archived is False:
    cache.set(key, messages)
  
  return messages


@line_profile
def get_unread_messages_count(session_id, user_id=None, topic_id=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  owner_id = get_user_id(session_id, db_name=db_name)
  if not owner_id:
    return False
  
  if user_id:
    user_id = int(user_id)
    last_viewed = get_last_viewed(owner_id, user_id, db_name=db_name)
    return db.message.find({'$or': [{'from': user_id, 'to': owner_id},
                                    {'from': owner_id, 'to': user_id}],
                            'ts': {'$gt': last_viewed}}).count()
  elif topic_id:
    topic_id = int(topic_id)
    last_viewed = get_last_viewed(owner_id, topic_id=topic_id, db_name=db_name)
    return db.message.find({'topic': topic_id,
                            'ts': {'$gt': last_viewed}}).count()
    
  else:
    count = 0
    records = db.message.find({'owner': owner_id, 
                               'user_id': {'$ne': None}})
    for record in records:
      user_id = record.get('user_id')
      count += get_unread_messages_count(session_id, user_id, db_name=db_name)
      
    records = db.message.find({'members': owner_id})
    for record in records:
      topic_id = record.get('_id')
      count += get_unread_messages_count(session_id, topic_id=topic_id, db_name=db_name)
    
    return count
  

@line_profile
def get_unread_messages(session_id, archived=False, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  owner_id = get_user_id(session_id, db_name=db_name)
  if not owner_id:
    return False
  
  key = '%s:%s:unread_messages' % (db_name, owner_id)
  if archived is False:
    out = cache.get(key)
    if out is not None:
      return out
  
  out = []
  
  if archived:
    records = db.message.find({'members': owner_id, 
                               'archived_by': owner_id})
  else:
    records = db.message.find({'owner': owner_id, 
                               'user_id': {'$ne': None}})
    for record in records:
      uid = record.get('user_id')
      count = get_unread_messages_count(session_id, uid, db_name=db_name)
      if count > 0:
        out.append({'sender': get_user_info(uid, db_name=db_name), 
                    'unread_count': count})
        
    records = db.message.find({'members': owner_id, 
                               'archived_by': {'$nin': [owner_id]}})
  for record in records:
    topic_id = record.get('_id')
    count = get_unread_messages_count(session_id, topic_id=topic_id, db_name=db_name)
    if count > 0:
      out.append({'topic': get_topic_info(topic_id, db_name=db_name), 
                  'unread_count': count})
  
  if archived is False:
    cache.set(key, out)
  return out
    
    
def get_last_viewed(owner_id, user_id=None, topic_id=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if user_id:
    info = db.message.find_one({'owner': owner_id, 'user_id': user_id})
  else:
    info = db.message.find_one({'owner': owner_id, 'topic_id': topic_id})
    
  if info:
    return info.get('last_viewed')
  else:
    return 0
  

def update_last_viewed(owner_id, user_id=None, topic_id=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  if user_id:
    db.message.update({'owner': owner_id, 'user_id': int(user_id)}, 
                      {'$set': {'last_viewed': utctime()}}, upsert=True)
  else:
    db.message.update({'owner': owner_id, 'topic_id': int(topic_id)}, 
                      {'$set': {'last_viewed': utctime()}}, upsert=True)
    
  
  if user_id:
    ts = utctime() + int(get_utcoffset(owner_id, db_name=db_name))
    ts = friendly_format(ts, short=True)
    if ts.startswith('Today'):
      ts = ts.split(' at ')[-1]
      
    info = {'html': 'Seen %s' % ts}
    info['chat_id'] = 'user-%s' % owner_id
    push_queue.enqueue(publish, user_id, 
                       event_type='seen-by', 
                       info=info, 
                       db_name=db_name)
    
  else:
    info = {}
    info['chat_id'] = 'topic-%s' % topic_id
    topic = get_topic_info(topic_id)
    seen_by = []
    for user_id in topic.member_ids:
      last_viewed = get_last_viewed(user_id, topic_id=topic_id, db_name=db_name)
      if last_viewed > get_last_message(topic_id).get('ts'):
        seen_by.append(user_id)
      
    if len(seen_by) == len(topic.member_ids):
      seen_by_everyone = True
    else:
      seen_by_everyone = False
      seen_by = [get_user_info(i) for i in seen_by]
      
    for user_id in topic.member_ids:
      if user_id != owner_id:
        if seen_by_everyone:
          info['html'] = 'Seen by everyone'
        else:
          info['html'] = 'Seen by %s' % (', '.join([i.name for i in seen_by \
                                                    if i.id != user_id]))
        push_queue.enqueue(publish, user_id, 
                           event_type='seen-by', 
                           info=info, 
                           db_name=db_name)
        
  key = '%s:%s:unread_messages' % (db_name, owner_id)
  cache.delete(key)
  
  key = '%s:%s:messages' % (db_name, owner_id)
  cache.delete(key)
  
  return True

def get_last_message(topic_id, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  msg = db.message.find({'topic': int(topic_id)}).sort('ts', -1).limit(1)
  if msg:
    return list(msg)[0]

@line_profile
def get_chat_history(session_id, user_id=None, topic_id=None, timestamp=None, db_name=None):
  if not db_name:
    db_name = get_database_name()
  db = DATABASE[db_name]
  
  owner_id = get_user_id(session_id, db_name=db_name)
  if not owner_id:
    return False
  
  if user_id and not str(user_id).isdigit():
    return False
  
  if user_id:
    user_id = int(user_id)
  
    query = {'$or': [{'from': owner_id, 'to': user_id},
                     {'from': user_id, 'to': owner_id}]}
    
  else:
    topic_id = int(topic_id)
    
    topic = get_topic_info(topic_id)
    if owner_id not in topic.member_ids:
      return False
    
    query = {'topic': topic_id}
    
    
  if timestamp:
    query['ts'] = {'$lt': float(timestamp)}
    
  
  records = db.message.find(query)\
                      .sort('ts', -1)\
                      .limit(50)
    
  records = list(records)
  records.reverse()
  if records and len(records) < 50:
    records[0]['is_first_message'] = True
  
  last_viewed = get_last_viewed(owner_id, user_id, topic_id, db_name)
  
  messages = []
  last_msg = None
  for record in records:
    msg = record.get('msg')
    if last_msg and \
      not last_msg.get('auto_generated') and \
      not record.get('auto_generated') and \
      record.get('from') == last_msg.get('from') and \
      (record.get('ts') - last_msg.get('ts')) < 120:
    
      if is_snowflake_id(msg):
        attachment = get_attachment_info(msg, db_name=db_name)
          
        msg = "<a href='/attachment/%s' target='_blank' title='%s (%s)' %s>%s (%s)</a>"\
            % (attachment.id, attachment.name, attachment.size, 
               '' if attachment.mimetype.startswith('image/') else "download='%s'" % attachment.name,
               attachment.name, attachment.size)
        if attachment.mimetype.startswith('image/'):
          msg += '''<a class='image-expander'>...</a>
          <div class='hidden'><a href='/attachment/%s' target="_blank" title='%s (%s)'><img src='/attachment/%s'></a></div>''' \
          % (attachment.id, attachment.name, attachment.size, attachment.id)
          
      elif record.get('codeblock'):
        msg = '<pre class="prettyprint">%s</pre>' % msg
      
      if '</' in msg or '</' in last_msg['text']:
        last_msg['text'] += '<br>' + msg
      else:
        last_msg['text'] += '\n' + msg
      last_msg['ts'] = record.get('ts')
      last_msg['msg_ids'].append(record.get('_id'))
    else:
      if last_msg:
        messages.append(last_msg)
      last_msg = record
      last_msg['msg_ids'] = [record['_id']]
      last_msg['_ts'] = record['ts']
      
      if is_snowflake_id(msg):
        attachment = get_attachment_info(msg, db_name=db_name)
        
        last_msg['text'] = "<a href='/attachment/%s' target='_blank' title='%s (%s)' %s>%s (%s)</a>"\
            % (attachment.id, attachment.name, attachment.size, 
               '' if attachment.mimetype.startswith('image/') else "download='%s'" % attachment.name,
               attachment.name, attachment.size)
            
        if attachment.mimetype.startswith('image/'):
          last_msg['text'] += '''<a class='image-expander'>...</a>
          <div class='hidden'><a href='/attachment/%s' target="_blank" title='%s (%s)'><img src='/attachment/%s'></a></div>''' \
          % (attachment.id, attachment.name, attachment.size, attachment.id)
      
      elif record.get('codeblock'):
        last_msg['text'] = '<pre class="prettyprint">%s</pre>' % msg
      
      else:
        last_msg['text'] = msg
  
  if last_msg:
    messages.append(last_msg)
    
  
  if messages and messages[-1].get('ts', 0) > last_viewed:
    messages[-1]['is_unread'] = True
  
  utcoffset = get_utcoffset(owner_id, db_name=db_name)
  return [Message(i, utcoffset=utcoffset, db_name=db_name) for i in messages]
      
    
  
  








