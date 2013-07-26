#! coding: utf-8
# pylint: disable-msg=W0311
#from lib import simple_detect
from os import path
from hashlib import md5
from urllib import urlencode
from mimetypes import guess_type
from xml.sax.saxutils import unescape
from httpagentparser import simple_detect

import re
import api
import filters
import settings




class Model:
  def __init__(self, info, db_name=None):
    self.info = info if info else dict()
    self.db_name = db_name
    
  @property
  def id(self):
    if self.info:
      return self.info.get("_id")
  
  @property
  def uuid(self):
    return self.info.get("_id")
  
  @property
  def timestamp(self):
    ts = self.info.get('timestamp', 0)
    if ts == 0:
      if self.info.has_key('history'):
        ts = self.info['history'][0].get('timestamp', 0)
    return ts
  
  @property
  def viewer_ids(self):
    return self.info.get('viewers', [])
    
  @property
  def viewers(self):
    viewers = self.info.get('viewers', [])
    user_ids = set()
    out = []
    is_public = False
    for user_id in viewers:
      if str(user_id).lower().strip() == 'public':
        is_public = True
      elif user_id and user_id not in user_ids:
        user_ids.add(user_id)
        user_info = api.get_owner_info_from_uuid(user_id, 
                                                 db_name=self.db_name)
        if user_info.id:
          out.append(user_info)
          
    out.sort(key=lambda k: k.is_group())
    if is_public:
      out.append(api.get_owner_info_from_uuid('public', 
                                              db_name=self.db_name))
    return out
  
  @property
  def seen_by(self):
    if not self.info:
      return []
    users = []
    user_ids = set()
    if self.info.get('read_receipts'):
      # dirty hack
      if self.info['owner'] == self.info['read_receipts'][0]['user_id']:
        self.info['read_receipts'].pop(0)
        
      for record in self.info.get('read_receipts')[::-1]:
        timestamp = record.get('timestamp')
        user_id = record.get('user_id')
          
        if user_id not in user_ids and not api.is_group(user_id, 
                                                        db_name=self.db_name):
          users.append({'user': api.get_user_info(user_id, 
                                                  db_name=self.db_name),
                        'timestamp': timestamp})
          user_ids.add(user_id)
    users.sort(key=lambda k: k.get('timestamp'), reverse=True)
    return users
    
        
  @property
  def read_receipt_ids(self):
    if self.info and self.info.get('read_receipts'):
      # lỗi từ hồi xưa (thiết kế db cũ)
      if isinstance(self.info['read_receipts'][0], int):
        self.info['read_receipts'].pop(0)
              
      user_ids = set()
      for record in self.info.get('read_receipts'):
        timestamp = record.get('timestamp')
        if timestamp > self.last_updated:
          user_id = record.get('user_id')
          user_ids.add(user_id)      
        
      return list(user_ids)
    else:
      return []
  
  @property
  def read_receipts(self):
    users = []
    user_ids = set()
    if self.info.get('read_receipts'):
      # dirty hack
      if self.info['owner'] == self.info['read_receipts'][0]['user_id']:
        self.info['read_receipts'].pop(0)
        
      for record in self.info.get('read_receipts'):
        timestamp = record.get('timestamp')
        if timestamp > self.last_updated:
          user_id = record.get('user_id')
            
          if user_id not in user_ids \
          and not api.is_group(user_id, db_name=self.db_name):
            users.append({'user': api.get_user_info(user_id, 
                                                    db_name=self.db_name),
                          'timestamp': timestamp})
            user_ids.add(user_id)
        
    users.sort(key=lambda k: k.get('timestamp'), reverse=True)
    return users
  
  @property
  def last_read_receipt(self):
    if self.info.get('read_receipts'):
      return self.info.get('read_receipts')[-1]
  
  @property
  def starred(self):
    return self.info.get('starred', [])
      
  @property
  def comments(self):
    comments = self.info.get('comments')
    comments.sort(key=lambda k: k.get('timestamp'))
#    return [Comment(i) for i in comments if not i.get('is_removed')]   
  
    comments_list = []
    for i in comments:
      if i.get('is_removed'):
        continue
      
      comment = Comment(i, db_name=self.db_name)
      if i.get('reply_to'):
        reply_to = i.get('reply_to')
        for j in comments:
          if j['_id'] == reply_to:
            comment.reply_src = Comment(j, db_name=self.db_name)
            break
      comments_list.append(comment)
    return comments_list
  
  
  @property
  def last_comments(self):
    comments = self.info.get('comments')
    comments.sort(key=lambda k: k.get('timestamp'), reverse=True)
    last_comments = []
    for comment in comments:
      if not comment.has_key('is_removed'):
        last_comments.append(Comment(comment, db_name=self.db_name))
      if len(last_comments) >= 2:
        break
    last_comments.reverse()
    return last_comments  
  
  @property
  def comments_count(self):
    if self.info.get('comments'):
      return len([i for i in self.info.get('comments') \
                  if not i.has_key('is_removed')])
    return 0
  
  @property
  def spam_count(self):
    if self.info.has_key('comments'):
      return len([i for i in self.info.get('comments') \
                  if i.has_key('is_spam')])
    return 0
  
  @property
  def owner(self):
    return api.get_user_info(self.info.get('owner'), db_name=self.db_name)
  
  @property
  def last_action(self):
    if not self.info:
      return History({})
    if (self.info.get('comments') and 
        self.last_updated <= self.info['comments'][-1]['timestamp']):
      info = {'action': 'commented',
              'owner': self.info['comments'][-1]['owner'],
              'timestamp': self.info['comments'][-1]['timestamp']}
    else:
      if self.info.get('filename'):
        info = self.info.get('history')[-1]
        if not info.has_key('attachment_id'):
          for i in self.info.get('history')[::-1]:
            if i.has_key('attachment_id'):
              info['attachment_id'] = i['attachment_id']
              break            
          
      elif self.info.has_key('history'):
        info = self.info.get('history')[-1]
        
      elif self.info.has_key('version'):
        versions = self.info.get('version')
        info = versions[-1]
        if len(versions) == 1:
          info['action'] = 'created'
        else:
          info['action'] = 'edited'
      else:
        info = {'action': 'adds',
                'owner': self.info.get('owner'),
                'timestamp': self.info.get('timestamp')}
      
    return History(info)
  
  @property
  def last_updated(self):
    return self.info.get('last_updated')
    
  
  @property
  def hashtags(self):
    return self.info.get('hashtags', [])
  
  def is_public(self):
    if 'public' in self.info.get('viewers', []):
      return True
    return False
  
  def is_email(self):
    if self.info and self.info.has_key('message_id'):
      return True
  
  def to_dict(self):
    return self.info
  
  @property
  def liked_user_ids(self):
    if self.id:
      return api.get_liked_user_ids(self.id, db_name=self.db_name)
    else:
      return []
  
  @property
  def liked_by(self):
    return [api.get_user_info(user_id, db_name=self.db_name) \
            for user_id in self.liked_user_ids]
  
  
class User(Model):
  def __init__(self, info, db_name=None):
    self.info = info if info else dict()
    self.db_name = db_name
  
  @property
  def name(self):
    return self.info.get('name') \
      if self.info.get('name') else self.email \
      if self.email else ''
  
  @property
  def email(self):
    email_addr = self.info.get('email', '')
    if email_addr and '@' in email_addr:
      return email_addr
  
  @property
  def verified(self):
    return self.info.get('verified','')
  
  
  @property
  def email_name(self):
    if '@' in self.email:
      return self.email.split('@', 1)[0]
  
  @property
  def email_domain(self):
    if '@' in self.email:
      return self.email.split('@', 1)[1]
  
  @property
  def avatar(self):
    avatar = self.info.get('avatar')
    
    if avatar and isinstance(avatar, str) or isinstance(avatar, unicode):
      if 'googleusercontent' in avatar:
        avatar = avatar.replace('/photo.jpg', '/s60-c/photo.jpg')
      return avatar
    elif avatar:
      attachment = api.get_attachment_info(avatar, db_name=self.db_name)
      filename = '%s_60.jpg' % attachment.md5
      if attachment.md5 and api.is_s3_file(filename, db_name=self.db_name):
        return 'http://%s.s3.amazonaws.com/%s' % (settings.S3_BUCKET_NAME, filename)
      
      return '/img/' + str(avatar) + '.jpg'
    
    # try gravatar
    default = "http://jupo.s3.amazonaws.com/images/user2.png"
    if not self.email:
      return default
    
    email = self.email.strip().lower()
    size = 50
    gravatar_url = "http://www.gravatar.com/avatar/" + md5(email.lower()).hexdigest() + "?"
    gravatar_url += urlencode({'d':default, 's':str(size)})
    return gravatar_url
  
  @property
  def introduction(self):
    return self.info.get('introduction')
    
  @property
  def gender(self):
    return self.info.get('gender')
    
  
  @property
  def birthday(self):
    if self.info.has_key('birthday'):
      parts = self.info.get('birthday').split('/')
      return {'day': parts[0], 'month': parts[1], 'year': parts[2]}
    else:
      return {}
  
  @property
  def created_at(self):
    return int(self.info.get('timestamp', 0))
    
  @property
  def utcoffset(self):
    return self.info.get('utcoffset', 0)
  
  
  @property
  def status(self):
    return api.check_status(self.id, db_name=self.db_name)
    
  @property
  def location(self):
    return self.info.get('location')
    

  @property
  def locale(self):
    return self.info.get('locale')
    
  @property
  def phone(self):
    return self.info.get('phone', '')
    
  @property
  def unfollow_posts(self):
    return [post_id for post_id in self.info.get('unfollow_posts', [])]   
    
  @property
  def last_login(self):
    info = self.info.get('history')
    if not info:
      return None
    elif len(info) == 1:
      info = info[-1]
    else:
      info = info[-2]
      
    if not info.get('user_agent'):
      return None
    os, browser = simple_detect(info.get('user_agent'))
    return {'timestamp': info.get('timestamp'),
            'os': os, 
            'browser': browser,
            'ip': info.get('remote_addr')}   
    
  @property
  def last_online(self):
    return api.last_online(self.id, db_name=self.db_name)
  
  @property
  def session_id(self):
    return self.info.get('session_id')
  
  @property
  def groups(self):
    return api.get_groups(self.info.get('session_id'), db_name=self.db_name)
  
  @property
  def groups_count(self):
    return api.get_groups_count(self.id, db_name=self.db_name)
  
  @property
  def followers(self):
#    return [api.get_user_info(user_id) for user_id in self.info.get('followers', [])] 
    return self.info.get('followers', [])
  
  @property
  def open_groups(self):
    return [i for i in self.groups if i.privacy == 'open']
  
  @property
  def following_users(self, info=False):
    return api.get_following_users(self.id, db_name=self.db_name)
  
  @property
  def contact_ids(self):
    return self.info.get('contacts', [])
  
  @property
  def contacts(self):
    users = [api.get_user_info(user_id, db_name=self.db_name) \
             for user_id in self.contact_ids]
    users.sort(key=lambda k: k.last_online, reverse=True)
    return users
  
  @property
  def following_details(self):
    return [api.get_user_info(user_id, db_name=self.db_name) \
            for user_id in api.get_following_users(self.info['_id'], 
                                                   db_name=self.db_name)]
  
  @property
  def starred_posts_count(self):
    return api.get_starred_posts_count(self.info['_id'], db_name=self.db_name)
    
  @property
  def email_addresses(self):
    return api.get_email_addresses(self.id, db_name=self.db_name)  
    
  def is_group(self):
    return False
  
  def is_registered(self):
    return True if self.info.get('password') else False
  
  def is_admin(self):
    return True if self.info.get('admin') else False
  
  def has_password(self):
    passwd = self.info.get('password')
    if passwd and not isinstance(passwd, bool):
      return True
    
  def has_google_contacts(self):
    return self.info.has_key('google_contacts')
  
  @property
  def fb_request_sent(self):
    return self.info.get('fb_request_sent')
  
  @property
  def google_contacts(self):
    return [User({'_id': api.get_user_id_from_email_address(email, 
                                                            db_name=self.db_name),
                  'email': email}) \
            for email in self.info.get('google_contacts', [])]
  

  
  @property
  def networks(self):
    out = api.get_networks(self.id, self.email)
    return out if out else []
    
    
  @property
  def disabled_notifications(self):
    return self.info.get('disabled_notifications', [])
  

class Comment(Model):
  def __init__(self, info, db_name=None):
    self.info = info if info else dict()
    self.db_name = db_name
  
  @property
  def owner(self):
    return api.get_user_info(self.info.get('owner'),
                             db_name=self.db_name)
  
  @property
  def message(self):
    if self.info.has_key('body'): # is email
      return self.info.get('body')
    if self.info.has_key('new_message'):
      return self.info.get('new_message')
    else:
      return self.info.get('message')
    
  @property
  def original_message(self):
    return self.info.get('message')
    
    # remove gmail quote (if is email)
#    message = message.split('<div class="gmail_quote">')[0]
#    
#    mentions = self.info.get('mentions')
#    if mentions:
#      for user in mentions:
#        message = message.replace(user.get('name'), 
#          '<a href="/user/%s" class="overlay">%s</a>' % (user.get('id'), user.get('name')))

  @property
  def last_edited_timestamp(self):
    return self.info.get('last_edited', 0)
    

  @property
  def changes(self):
    return api.diff(self.original_message, self.message)

  def is_removed(self):
    return self.info.get('is_removed')

  def is_edited(self):
    return self.info.has_key('new_message')
  
  def is_spam(self):
    return self.info.get('is_spam')
  
  def is_email(self):
    return self.info.get('message_id')
  
  @property
  def message_id(self):
    return self.info.get('message_id')
  
  @property
  def reply_to(self):
    return self.info.get('reply_to')
  
  @property
  def reply_src(self):
    return None
  
  @property
  def urls(self):
    return [api.get_url_info(u, db_name=self.db_name) \
            for u in api.extract_urls(self.message)]
  
  @property
  def post_id(self):
    return self.info.get('post_id')
  
  @property
  def attachments(self):
    return [api.get_attachment_info(attachment_id, db_name=self.db_name) \
            for attachment_id in self.info.get('attachments', [])]
  
  @property
  def attachment_ids(self):
    return self.info.get('attachments', [])
  
  

class Reminder(Model):
  def __init__(self, info):
    self.info = info
    
  @property
  def message(self):
    return self.info.get('message', '')
  
  @property
  def is_checked(self):
    return self.info.get('checked')


    

class Attachment(Model):
  def __init__(self, info, db_name=None):
    self.info = info if info else dict()
    self.db_name = db_name
  
  @property
  def fid(self):
    return self.info.get('fid')
  
  @property
  def name(self):
    return self.info.get('name', '')
  
  @property
  def size(self):
    return api.sizeof(self.info.get('size', 0))
  
  @property
  def raw_size(self):
    return self.info.get('size', 0)
  
  @property
  def mimetype(self):
    mime = guess_type(self.name)[0]
    return mime if mime else ''
    
  def is_attached(self):
    return self.info.get('is_attached')
  
  @property
  def md5(self):
    return self.info.get('md5')
  
  @property
  def download_url(self):
    return api.s3_url(self.md5, content_type=self.mimetype, 
                      disposition_filename=self.name)
  
  @property
  def serving_url(self):
    return api.s3_url(self.md5, content_type=self.mimetype)
  
  
  @property
  def icon(self):
    ext = self.name.rsplit('.', 1)[-1].lower()
    icon_path = 'public/images/icons/%s.png' % ext
    if path.isfile(icon_path):
      return 'https://s3.amazonaws.com/5works/icons/%s.png' % ext
    else:
      return 'https://s3.amazonaws.com/5works/icons/generic.png'


  
class File(Model):
  def __init__(self, info, db_name=None):
    self.info = info if info else dict()
    self.db_name = db_name
  
  @property
  def history(self):
    return [History(i) for i in self.info.get('history')[::-1][:5]]
  
  @property
  def attachment_id(self):
    for i in self.info.get('history')[::-1]:
      if i.has_key('attachment_id'):
        return i.get('attachment_id')
  
  @property
  def details(self):
    return api.get_attachment_info(self.attachment_id, 
                                   db_name=self.db_name)
  
  @property
  def name(self):
    if self.info.has_key('filename'):
      return self.info['filename']
    return api.get_attachment_info(self.attachment_id, 
                                   db_name=self.db_name).name
  
  @property
  def extension(self):
    return self.name.rsplit('.')[-1].lower()
  
  @property
  def size(self):
    return api.sizeof(self.raw_size)
  
  @property
  def diff(self):
    try:
      old = api.get_attachment_info(self.info['history'][-2]['attachment_id'], 
                                    db_name=self.db_name).raw_size
    except (IndexError, KeyError):
      return None
    new = self.raw_size
    delta = new - old
    if delta > 0:
      return '+%s' % api.sizeof(delta)
    else:
      return '-%s' % api.sizeof(abs(delta))
  
  @property
  def raw_size(self):
    return self.details.raw_size
  
  @property
  def timestamp(self):
    ts = self.info.get('history')[-1].get('timestamp')
    return ts
  
  @property
  def owner(self):
    return self.info.get('history')[-1].get('owner')
      
  @property
  def mimetype(self):
    mime = guess_type(self.name)[0]
    return mime if mime else ''
    
  @property
  def icon(self):
    ext = self.name.rsplit('.', 1)[-1].lower()
    icon_path = 'public/images/icons/%s.png' % ext
    if path.isfile(icon_path):
      return '/public/images/icons/%s.png' % ext
    else:
      return '/public/images/icons/generic.png'

      

class Group(Model):
  def __init__(self, info, db_name=None):
    self.info = info if info else dict()
    self.db_name = db_name
       
  @property
  def name(self):
    return self.info.get('name')
  
  @property
  def logo(self):    
    file_id = self.info.get('avatar')
    if file_id:
      return '/img/128/' + str(file_id) + '.png'
    return 'https://s3.amazonaws.com/5works/images/avatar.96.gif'
  
  @property
  def last_5_members(self):
    members = self.info.get('members')
    if members:
      members = list(set(members))[-5:]
      members = [api.get_user_info(user_id, db_name=self.db_name) \
                 for user_id in members]
      members = sorted(members, key=lambda k: k.last_online, reverse=False)
      return members
  
  @property
  def privacy(self):
    state = self.info.get('privacy', 'closed')
    return state
  
  
  @property
  def members_count(self):
    return len(self.info.get('members', []))
  
  @property
  def members(self):
    members = self.info.get('members')
    if members:
      members = set(members)
      members = [api.get_user_info(user_id, db_name=self.db_name) \
                 for user_id in members]
      if self.id == 'public':
        members = sorted(members, key=lambda k: k.timestamp, reverse=True)
      else:
        members = sorted(members, key=lambda k: k.last_online, reverse=True)
      
      return members
    else:
      return []
    
  @property
  def pending_members(self):
    pending_members = self.info.get('pending_members', [])
    return [api.get_user_info(user_id, db_name=self.db_name) \
            for user_id in pending_members]
    
  
  @property
  def pending_member_ids(self):
    return self.info.get('pending_members', [])
    
    
  @property
  def leaders(self):
    return [api.get_user_info(user_id, db_name=self.db_name) \
            for user_id in self.info.get('leaders')]
  
  @property
  def administrator_ids(self):
    return [user_id for user_id in self.info.get('leaders', [])]
  
  @property
  def member_ids(self):
    return [user_id for user_id in self.info.get('members', [])]
    
  @property
  def administrators(self):
    return [api.get_user_info(user_id, db_name=self.db_name) \
            for user_id in self.info.get('leaders', [])]
  
  @property
  def about(self):
    return self.info.get('about', '')
  
  @property
  def recently_viewed(self):
    records = self.info.get('recently_viewed', [])
    user_ids = []
    users = []
    records.reverse()
    for record in records:
      if not record:
        continue
      user_id = record['user_id']
      if user_id and user_id not in user_ids:
        user_ids.append(user_id)
        user = api.get_user_info(user_id, db_name=self.db_name)
        if user.id:
          users.append({'user': user,
                        'timestamp': record['timestamp']})
          
          if len(users) >= 5:
            break
    
    return users
  
  def is_group(self):
    return True
  
  @property
  def post_permission(self):
    return self.info.get('post_permission', 'members')
  
  @property
  def highlights(self):
    return [api.Note(api.get_record(i, db_name=self.db_name)) \
            for i in self.highlight_ids]
  
  @property
  def highlight_ids(self):
    return self.info.get('highlights', [])
  

class Note(Model):
  def __init__(self, info, version=-1, db_name=None):
    self.info = info if info else dict()
    self.version_index = version
    self.db_name = db_name
    
  @property
  def title(self):
    versions = self.info.get('version')
    if not versions:
      return 'Untitled Note'
    info = versions[self.version_index]
    return info.get('title', 'Untitled Note')
    
  
  @property
  def version(self):
    version = self.info.get('version')
    version.reverse()
    version = [Version(i, db_name=self.db_name) for i in version]
    version.reverse()
    return version
  
  @property
  def raw_content(self):
    return self.info.get('version')[self.version_index].get('content')
  
  @property
  def content(self):
    content = self.info.get('version')[self.version_index].get('content')
    
    return content
    
#    lines = content.replace('<br>', '\n').strip().split('\n')
#    if len(lines) == 1:
#      content = content.split('. ', 1)[-1]
#    elif len(lines[0]) < 100:
#      content = '\n'.join(lines[1:])
#    
#    tags = self.info.get('version')[-1].get('tags')
#    if tags:
#      for tag in tags:
#        content = content.replace(tag.get('name'), 
#                                  '<a href="/%s">%s</a>' % (tag.get('id'), 
#                                                            tag.get('name')))
#    return content.strip()
  
  @property
  def owner(self):
    return api.get_user_info(self.info.get('version')[self.version_index].get('owner'), 
                             db_name=self.db_name)
  
  @property
  def timestamp(self):
    return self.info.get('version')[self.version_index].get('timestamp')
    
  @property
  def attachments(self):
    return [api.get_attachment_info(attachment_id, db_name=self.db_name) \
            for attachment_id in self.info.get('attachments', [])]
      
  @property
  def diff(self):
    stat = api.diff_stat(self.id)
    changes = stat['additions'] + stat['deletions']
    if changes <= 5:
      stat['+'] = stat['additions']
      stat['-'] = stat['deletions']
    else:
      stat['+'] = int(stat['additions'] / float(changes) * 5)
      stat['-'] = int(stat['deletions'] / float(changes) * 5)
    
    stat['.'] = 5 - stat['+'] - stat['-']
    return stat
  
  @property
  def key(self):
    return self.info.get('key')
  
  def is_official(self):
    return self.info.get('is_official')
  
  

class Version(Model):
  def __init__(self, info, db_name=None):
    self.info = info if info else dict()
    self.db_name = None
  
  @property
  def owner(self):
    return api.get_user_info(self.info.get('owner'), db_name=self.db_name)
    
  
class Feed(Model):
  def __init__(self, info, db_name=None):
    self.info = info
    self.db_name = db_name
    
  @property
  def raw_message(self):
    return self.info.get('message')    
      
  @property
  def message(self):
    if self.is_system_message():
      msg = self.info.get('new_message', self.info.get('message', ''))
      if msg.get('group_id'):
        msg['group'] = api.get_owner_info_from_uuid(msg['group_id'], 
                                                    db_name=self.db_name)
      if msg.get('user_id'):
        msg['user'] = api.get_owner_info_from_uuid(msg['user_id'],
                                                   db_name=self.db_name)
      return msg
      
    if self.is_file():
      return File(self.info).name
    if self.is_event():
      return self.info.get('name', '')
    if self.is_email():
      return self.info.get('subject', '')
    
    message = self.info.get('new_message', self.info.get('message', ''))
    
    return message
    
  @property
  def original_message(self):
    return self.info.get('message')

  @property
  def last_edited_timestamp(self):
    return self.info.get('last_edited', 0)

  @property
  def changes(self):
    return api.diff(api.filters.clean(self.original_message), self.message)
  
  @property
  def owner(self):
    return api.get_owner_info_from_uuid(self.info.get('owner'), 
                                        db_name=self.db_name)
  
  
  @property
  def datetime(self):
    if self.info.get('version'):  # is doc
      ts = self.info.get('version')[-1].get('timestamp')
    elif self.info.get('history'):  # is doc
      ts = self.info.get('history')[-1].get('timestamp')
    else:
      ts = self.info.get('timestamp')
    
    ts = api.datetime.fromtimestamp(int(ts))
    return ts.strftime('%A, %B %d, %Y at %I:%M %p')
  
  @property
  def details(self):
    if self.info.has_key('version'):
      self.info['version'] = sorted(self.info['version'], key=lambda k:k['timestamp'])
      return Note(self.info, db_name=self.db_name)
    elif self.info.has_key('when'):
      return Event(self.info)
    elif self.info.has_key('history') and self.info.get('history')[0].has_key('attachment_id'):
      return File(self.info)
    else:
      return Feed(self.info, db_name=self.db_name)
  
  @property
  def urls(self):
    if self.info.has_key('urls'):
      return [api.get_url_info(url, db_name=self.db_name) \
              for url in self.info.get('urls')]
    else:
      return []
    
  @property
  def attachment_ids(self):
    if self.info.has_key('history') and \
       self.info['history'][0].has_key('attachment_id'):
      return [i['attachment_id'] \
              for i in self.info['history'] \
              if i.has_key('attachment_id')]
    return self.info.get('attachments', [])
    
  @property
  def attachments(self):
    if self.info.has_key('attachments'):
      return [api.get_attachment_info(attachment_id, db_name=self.db_name) \
              for attachment_id in self.info.get('attachments')]
  
  def is_edited(self):
    return True if self.info.has_key('new_message') else False
  
  def is_task(self):
    if self.info and self.info.get('priority') is not None:
      return True
    return False
  
  def is_file(self):
    if self.info and self.info.has_key('history') \
      and self.info.get('history')[0].get('attachment_id'):
      return True
    return False
  
  def is_note(self):
    if self.info and self.info.get('version'):
      return True
    
  def is_event(self):
    if self.info and self.info.get('when'):
      return True
  
  def is_gitlab_commit(self):
    if (not self.is_system_message() and 
        self.message.strip() and
        self.message.strip()[0] == '{' 
        and 'commits' in self.message
        and 'github.com' not in self.message):
      return True
    
  def is_github_commit(self):
    if (not self.is_system_message() and 
        self.message.strip() and
        self.message.strip()[0] == '{' 
        and 'commits' in self.message
        and 'github.com' in self.message):
      return True
    
  def is_system_message(self):
    if self.info and isinstance(self.info.get('message'), dict):
      return True
  
  @property
  def rel(self):
    if self.is_task():
      return 'focus'
    elif self.is_file():
      return 'file'
    elif self.is_note():
      return 'doc'
#    elif self.is_event():
#      return 'event'
    else:
      return 'feed'
    
  @property
  def message_id(self): # is email
    return self.info.get('message_id')
  
  @property
  def body(self): # is email
    return self.info.get('body', '')
  
  @property
  def email_addresses(self):
    receivers = self.info.get('receivers', [])
    receivers.append(self.info.get('sender'))
    addrs = set()
    for i in receivers:
      if '<' in i and '>' in i and '@' in i and '.' in i:
        addrs.add(i.rsplit(' ', 1)[-1].strip('<>'))
      elif '@' in i and '.' in i:
        addrs.add(i)
    return list(addrs)
  
  @property
  def archived_by(self):
    return self.info.get('archived_by', [])
  
  @property
  def starred_by(self):
    return [api.get_user_info(user_id, db_name=self.db_name) \
            for user_id in self.info.get('starred', [])[-5:]]
  
  @property
  def pinned_by(self):
    return self.info.get('pinned', [])
  
  @property
  def stats(self):
    info = {}
    for comment in self.info.get('comments', []):
      user_id = comment.get('owner')
      if info.has_key(user_id):
        info[user_id] += 1
      else:
        info[user_id] = 1
    
    owner_id = self.info.get('owner')
    if info.has_key(owner_id):
      info[owner_id] += 1
    else:
      info[owner_id] = 1
    
    out = []
    for user_id in info.keys():
      out.append({'user': api.get_user_info(user_id, db_name=self.db_name),
                  'post_count': info[user_id]})
    
    out.sort(key=lambda k: k['post_count'], reverse=True)
    return out
    


class History(Model):
  def __init__(self, info, db_name=None):
    self.info = info if info else dict()
    self.db_name = db_name
  
  @property
  def owner(self):
    user_id = self.info.get('user_id', self.info.get('owner'))
    return api.get_user_info(user_id, db_name=self.db_name)  
  
  @property
  def user(self):
    user_id = self.info.get('user_id', self.info.get('owner'))
    return api.get_user_info(user_id, db_name=self.db_name)  
    
  @property
  def action(self):
    return self.info.get('action', 'updated')
  
  @property
  def message(self):
    if self.info.has_key('attachment_id'):
      attachment = api.get_attachment_info(self.info['attachment_id'], 
                                           db_name=self.db_name)
      return attachment.name
    else:
      return self.info.get('message')
    
  @property
  def ref_info(self):
    if self.info.has_key('attachment_id'):
      return api.get_attachment_info(self.info['attachment_id'], 
                                     db_name=self.db_name)
    
  
  @property
  def timestamp(self):
    return self.info.get('timestamp')
  
  
class URL(Model, Feed):
  def __init__(self, info):
    self.info = info if info else dict()
    
  @property
  def url(self):
    return self.info.get('url')
  
  @property
  def domain(self):
    url = self.info.get('url').replace('http://', '').replace('https://', '')
    return url.split('/', 1)[0]
  
  def is_image(self):
    if re.compile('.*\.(?:jpe?g|gif|png)$').match(self.url.rsplit('?', 1)[0]):
      return True
    
  @property
  def basename(self):
    return path.basename(self.url.rsplit('?', 1)[0])
  
  @property
  def title(self):
    return self.info.get('title', '')
  
  @property
  def description(self):
    if self.text:
      return self.text
    else:
      description = self.info.get('description')
      if not description:
        description = ''
      return description
    
  @property
  def tags(self):
    tags = self.info.get('tags')
    hashtags = []
    if tags:
      for tag in tags:
        info = {'id': tag.strip().lower(),
                'name': '#' + tag.strip()}
        hashtags.append(info)
    return hashtags
      
  
  @property
  def favicon(self):
    favicon = self.info.get('favicon')
    if not favicon:
      return 'https://s3.amazonaws.com/5works/images/default_favicon.png'
    elif favicon.startswith('/'):
#      return '/proxy/' + self.domain + favicon
      return 'http://' + self.domain + favicon
    else:
      return favicon #.replace('https://', '/proxy/') 
  
  @property
  def size(self):
    return api.sizeof(self.info.get('size', 0))
  
  @property
  def raw_size(self):
    return self.info.get('size', 0)
  
  @property
  def img_src(self):
    url = self.info.get('img_src', '')
#    if url and not url.startswith('https://'):
#      url = url.replace('http://', '/proxy/') 
    return url
  
  @property
  def img_size(self):
    return self.info.get('img_size')
  
  @property
  def img_bytes(self):
    return api.sizeof(self.info.get('img_bytes'))
  
  @property
  def text(self):
    return self.info.get('text')


class Result(Model):
  def __init__(self, info, query=None, db_name=None):
    self.info = info if info else dict()
    self.query = query.strip()
    self.db_name = db_name
    
  @property
  def title(self):
#    if self.info.has_key('urls'):
#      url = self.info.get('urls')[0]
#      info = api.get_url_info(url)
#      return info.title
    if self.info.has_key('message'):
      return self.info.get('message').split('\n')[0]
    elif self.info.has_key('version'):
      return self.info.get('version')[-1].get('content').split('\n')[0]
  
  @property
  def content(self):
    if self.info.has_key('message'):
      return self.info.get('message')
    elif self.info.has_key('version'):
      return self.info.get('version')[-1].get('content')
    
  @property
  def owner(self):
    if self.info.has_key('message'):
      return api.get_user_info(self.info.get('owner'))
    else:
      return api.get_user_info(self.info.get('version')[-1].get('owner'))
    
  @property
  def type(self):
    if self.info.has_key('version'):
      return 'doc'
    elif self.info.has_key('priority'):
      return 'task'
    elif self.info.get('attachments'):
      return 'attachments'
    else:
      return 'feed'
  
  @property
  def details(self):
    if self.type == 'note':
      return Note(self.info)
    elif self.type == 'feed':
      return Feed(self.info, db_name=self.db_name)
    
  @property
  def viewers(self):
    if self.info.has_key('viewers'):
      viewers_list = [api.get_user_info(user_id) for user_id in self.info.get('viewers')]
      groups = users = []
      for i in viewers_list:
        if i.is_group():
          groups.append(i)
        else:
          users.append(i)
      users.extend(groups)
      return users
      
    
  @property
  def timestamp(self):
    return int(self.info.get('last_updated'))
      
  
  @property
  def description(self):
    if self.info.has_key('urls'):
      url = self.info.get('urls')[0]
      info = api.get_url_info(url)
      text = info.description
    elif self.info.has_key('message'):
      text = self.info.get('message')
    elif self.info.has_key('version'):
      text = self.info.get('version')[-1].get('content')
    if not text:
      return ''
    
    query = api.re.compile(self.query, api.re.IGNORECASE)
    description = []
    sentences = text.split('.')
    for sentence in sentences:
      if query.findall(sentence):
        s = query.sub('<b>%s</b>' % self.query, sentence.strip())
        description.append(s)
      else:
        sep_char = '... '
      if len(description) == 1:
        sep_char = '. '
      elif len(description) > 2:
        break

    description = sep_char.join(description)
    return description + '...'
  

class Message(Model):
  def __init__(self, info, utcoffset=0, db_name=None):
    self.info = info
    self.db_name = db_name
    self.utcoffset = int(utcoffset)
    
  @property
  def sender(self):
    user_id = self.info.get('from')
    if user_id:
      return api.get_user_info(user_id, db_name=self.db_name)
  
  @property
  def receiver(self):
    user_id = self.info.get('to')
    return api.get_user_info(user_id, db_name=self.db_name)
  
  @property
  def receivers(self):
    if self.topic_id:
      return self.topic.members
    else:
      return [self.receiver]
  
  @property
  def topic_id(self):
    return self.info.get('topic')
  
  @property
  def topic(self):
    topic_id = self.info.get('topic')
    if topic_id:
      return api.get_topic_info(topic_id, db_name=self.db_name)
  
  @property
  def content(self):
    if self.info.has_key('text'):
      return self.info.get('text')
    
    message = self.info.get('msg')
    if isinstance(message, int) or isinstance(message, long): # is file
      return api.get_attachment_info(message, db_name=self.db_name)
    return message
  
  @property
  def timestamp(self):
    return self.info.get('ts', 0) + self.utcoffset
  
  @property
  def _ts(self):
    return self.info.get('_ts')
    
  @property
  def date(self):
    return api.friendly_format(self.timestamp, short=True).split(' at ')[0]
  
  @property
  def time(self):
    return api.friendly_format(self.timestamp, short=True).split(' at ')[-1]
  
  @property
  def message_ids(self):
    return ','.join([str(i) for i in self.info.get('msg_ids', [self.id])])
  
  def get_date(self, short=False):
    return api.friendly_format(self.timestamp, short=short).split(' at ')[0]
  
  def is_file(self):    
    if self.info.has_key('text'):
      return False
    
    message = self.info.get('msg')
    if api.is_snowflake_id(message):
      return True
    
  def is_unread(self):
    return self.info.get('is_unread')
  
  def is_auto_generated(self):
    return self.info.get('auto_generated')
  
  def is_first_message(self):
    return self.info.get('is_first_message')
  
  def is_codeblock(self):
    return self.info.get('codeblock')
    

class Topic(Model):
  def __init__(self, info):
    self.info = info
    
  @property
  def name(self):
    return self.info.get('name')
    
  @property
  def member_ids(self):
    if self.info:
      return list(set(self.info.get('members', [])))
    else:
      return []
    
  @property
  def members(self):
    return [api.get_user_info(user_id) for user_id in self.member_ids]

  @property
  def archived_by(self):
    return self.info.get('archived_by', [])
  

class ESResult(Model):
  def __init__(self, info, query, db_name=None):
    self.query = query.strip()
    self.info = info if info else dict()
    self.db_name = db_name

  @property
  def owner(self):
    return api.get_user_info(self.info.get('owner'))
  
  @property
  def type(self):
    if self.info.get('version'):
      return 'doc'
    elif self.info.get('when'):
      return 'event'
    elif self.info.get('priority') is not None:
      return 'task'
    elif self.info.has_key('history') \
      and self.info.get('history')[0].has_key('attachment_id'):
      return 'file'
    else:
      return 'feed'
    
  @property
  def details(self):
    if self.info.get('when'):
      return Event(self.info)
    elif self.info.get('version'):
      return Note(self.info)
    elif self.type == 'file':
      return File(self.info)
    else:
      return Feed(self.info, db_name=self.db_name)
  
  
#  @property
#  def description(self):
#    text = self.content
#    
#    query = api.re.compile(self.query, api.re.IGNORECASE)
#    description = []
#    sentences = text.split('.')
#    for sentence in sentences:
#      if query.findall(sentence):
#        s = query.sub('<b>%s</b>' % self.query, sentence.strip())
#        description.append(s)
#      else:
#        sep_char = '... '
#      if len(description) == 1:
#        sep_char = '. '
#      elif len(description) > 2:
#        break
#
#    description = sep_char.join(description)
#    return description + '...'
  
  
class Notification(Model):
  def __init__(self, info, utcoffset, db_name):
    self.info = info if info else dict()
    self.offset = utcoffset
    self.db_name = db_name
    
  @property
  def sender(self):
    return api.get_user_info(self.info.get('sender'), db_name=self.db_name)
    
  @property
  def receiver(self):
    return api.get_user_info(self.info.get('receiver'), db_name=self.db_name)
  
  @property
  def item(self):
    record = api.get_record(self.ref_id, 
                            self.info.get('ref_collection', 'stream'), 
                            db_name=self.db_name)
    if not record or record.has_key('is_removed'):
      return Feed({})
    if self.comment_id:
      info = Feed(record, db_name=self.db_name)
      for i in info.comments:
        if i.id == self.comment_id:
          info.message = i.message
          info.owner = i.owner
          info.timestamp = i.timestamp
          break
    elif record.has_key('version'):
      info = Note(record, db_name=self.db_name)
      info.message = info.title
    elif record.has_key('when'):
      info = Event(record)
      info.message = info.name
    elif record.has_key('members'):
      info = Group(info, db_name=self.db_name)
    elif record.has_key('password'):
      info = User(info, db_name=self.db_name)
    else:
      info = Feed(record, db_name=self.db_name)
    return info
      
  @property
  def details(self):
    if self.ref_id == 'public':
      info = api.get_network_info(self.db_name)
      return info
    
    if self.info.get('type') == 'new_network':
      info = api.get_network_info(self.ref_id)
      return info
    
    record = api.get_record(self.ref_id, 
                            self.ref_collection, 
                            db_name=self.db_name)
      
    if not record or record.has_key('is_removed'):
      return None
    elif record.has_key('members'):
      info = Group(record, db_name=self.db_name)
    elif record.has_key('password'):
      info = User(record, db_name=self.db_name)
    else:
      info = Feed(record, db_name=self.db_name)
    return info
  
  @property
  def type(self):
    return self.info.get('type')
  
  @property
  def group(self):
    notification_type = self.info.get('type')
    if notification_type == 'conversation':
      return 'Direct Messages'
    elif notification_type == 'message':
      return 'Messages'
    elif notification_type == 'mention':
      return 'Mentions'
    elif notification_type == 'comment':
      return 'Responses'
    else:
      return notification_type
  
  @property
  def date(self):
    ts = self.info.get('timestamp', 0) + int(self.offset)
    text = filters.friendly_format(ts, short=True)
    if ' at ' in text:
      text = text.split(' at ')[0].strip()
    return text
  
  @property
  def ref_id(self):
    return self.info.get('ref_id')
  
  @property
  def ref_collection(self):
    collection = self.info.get('ref_collection', 'stream')
    if isinstance(collection, int) or isinstance(collection, long):
      collection = 'stream'
    return collection
  
  @property
  def comment_id(self):
    return self.info.get('comment_id')
  
  def is_unread(self):
    return self.info.get('is_unread')
  

  
          

class Event(Model):
  def __init__(self, info):
    self.info = info if info else dict()
    
  @property
  def name(self):
    return self.info.get('name').strip()
  
  @property
  def details(self):
    return self.info.get('details').strip()
  
  @property
  def when(self):
    return self.info.get('when')
  
  @property
  def where(self):
    return self.info.get('where') 
  
  @property
  def day(self):
    return '%02d' % api.datetime.fromtimestamp(self.when).day   
  
  @property
  def month_name(self):
    return api.datetime.fromtimestamp(self.when).strftime('%b')
  
  @property
  def time(self):
    return api.datetime.fromtimestamp(self.when).strftime('%I:%M%p').replace(' 0', ' ').replace('AM', 'am').replace('PM', 'pm')
    
  

class Browser(Model):
  def __init__(self, user_agent):
    self.user_agent = user_agent
    self.info = simple_detect(user_agent)
    
  @property
  def browser(self):
    return self.info[1]
  
  @property
  def os(self):
    return self.info[0]
  
  def is_firefox(self):
    if 'firefox' in self.browser.lower():
      return True
  
  
  
  
  
  
  
  