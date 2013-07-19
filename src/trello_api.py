# ! coding: utf-8
import urllib
import json
import httplib
import urllib2
import requests
import sys
import re
import api
from rq import Queue
from compiler.syntax import check
import time
# TRELLO_APP_KEY = '950ba9d46c41d2bf9de1e89b57df68ca'
# ID_BOARDS_JUPO = '51d6377f4b4cbf2f3f004068'
# TOKEN = '3dfd9ea21d521b3f019d9d1757cf4bc95f0044c12e9ac9af7ada1cafe6937a0d'

URL_DATA = 'https://trello.com/1/boards/%s?actions=all&actions_limit=20&key=%s&token%s'

db_name = api.get_database_name()
db = api.DATABASE[db_name]

LENG_LIST_ID_IN_FILE = 20

DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
EMAIL_JUPO = 'trello@trello.com'
PASS_JUPO = 'x7w7eeptvt'

class TrelloAction(object):
  def __init__(self, action, action_before=None, action_after=None):
    self.action = action
    self.action_before = action_before
    self.action_after = action_after
    
    self.action_data = TrelloActionData(action['data'])
    self.action_before_data = TrelloActionData(action_before['data'])
    self.action_after_data = TrelloActionData(action_after['data'])
    
  def __unicode__(self):
    return json.dumps(self.action)

  def __str__(self):
    return unicode(self).encode('utf-8')

  @property
  def type(self):
    return self.action['type']

  @property
  def member_fullname(self):
    return self.action['memberCreator']['fullName']

  @property
  def data(self):
    return self.action_data

  @property
  def timestamp(self):
    return datetime.datetime.strptime(self.action['date'], DATE_FORMAT)

  def get_trello_message(self):
    msg = ''
    print self.type
    if self.type == 'addAttachmentToCard' and self.action_after:
      if self.action_after['type'] == 'createCard':
        msg = self.member_fullname + ' added ' + self.action_data.card_name + \
              ' to ' + self.action_after_data.list_name + ' and attached ' + \
              self.action_data.name_file_attached
        return msg
      else:
        msg = self.member_fullname + ' attached ' + self.action_data.name_file_attached() + ' to ' + \
              self.action_data.card_name
        return msg
    
    if self.type == 'createCard' and self.action_before:
      if self.action_before['type'] != 'addAttachmentToCard':
        msg = self.member_fullname + ' added ' + self.action_data.card_name + ' to ' + \
              self.action_data.list_name
        return msg
      
    if self.type == 'updateCard' and not self.action['data'].has_key('listBefore'):
      return ''
    
    if self.type == 'updateCard' and self.action['data'].has_key('listBefore'):
      msg = self.member_fullname + ' moved ' + self.action_data.card_name + ' from ' + \
            self.action_data.list_before_name + ' to ' + self.action_data.list_after_name
      return msg
    
    if self.type == 'addMemberToCard':
      msg = self.action['memberCreator']['fullName'] + ' added ' + self.action['member']['fullName'] + \
            ' to ' + self.action_data.card_name
    
      return msg
    if self.type == 'commentCard':
      msg = self.member_fullname + ' comment "' + self.action_data.text
      return msg
    
    return ''
            
class TrelloActionData(object):
  def __init__(self, data):
    self.data = data
  
  @property
  def url_file_attached(self):
    return self.data['attachment']['url']
  
  @property
  def name_file_attached(self):
    return self.data['attachment']['name']
  
  @property
  def board_name(self):
    return self.data['board']['name']

  @property
  def card_name(self):
    return self.data['card']['name']

  @property
  def list_name(self):
    return self.data['list']['name']

  @property
  def list_before_name(self):
    return self.data['listBefore']['name']

  @property
  def list_after_name(self):
    return self.data['listAfter']['name']

  @property
  def text(self):
    return self.data['text']

  @property
  def check_item_name(self):
    return self.data['checkItem']['name']

  def check_item_state(self):
    return self.data['checkItem']['state']


def check_new_notification(id_notification):
  query = {'notification_trello': {'$elemMatch': {'id': id_notification}}}
  info_query = db.owner.find_one(query)
  if info_query:
    return False
  return True
  
  
  

def get_notifications_trello(trello_app_key, trello_token, trello_board_id, id_viewers):
  url_data = URL_DATA % (trello_board_id, trello_app_key, trello_token)
  data = urllib.urlopen(url_data % ()).read()
  data = json.loads(data)
  list_message = []
  list_new_id_notification = []
  for i in range(0,len(data['actions']) - 1):
    data_action = data['actions'][i]
    
    if check_new_notification(data_action['id']) == True:
      list_new_id_notification.append(data_action['id'])
      data_action_before = data_action_after = None
      try:
        data_action_before = data['actions'][i-1]
      except:
        pass
      try:
        data_action_after = data['actions'][i+1]
      except:
        pass
        
      action = TrelloAction(data_action, data_action_before, data_action_after)
      msg = action.get_trello_message()
      if msg:
        info_card = {}
        info_card['message'] = msg
        info_card['id'] = data_action['data']['card']['id']
        info_card['type'] = data_action['type']
        list_message.append(info_card)
        
  #day het id notification vao database
  array_info = []
  for id in list_new_id_notification:
    info = {}
    info['id'] = id
    info['timestamp'] = time.time()
    array_info.append(info)
  
  if array_info:
    db.owner.update({'trello_board_id': trello_board_id}, 
                    {'$pushAll': {'notification_trello': array_info}})
  
  
  # UPDATE them truong id_card_trello toi id_post_message
  # moi commend.type ma la kieu comment thi tim feed
  for info_card in reversed(list_message):
    if info_card['type'] != 'commentCard':
      id_post_message = api.post_message_trello('trello', info_card['message'], id_viewers)
      if id_post_message:
        api.add_id_trello_to_stream(id_post_message, info_card['id'])
    else:
      api.comment_message_trello(info_card['message'], info_card['id'])


def push_notification_trello():
  query = {'trello_app_key': {'$ne': None}}
  groups = db.owner.find(query)
  if groups:
    for group in groups:
      if group.has_key('trello_token') and group.has_key('trello_board_id'):
        trello_app_key = group['trello_app_key']
        trello_token = group['trello_token']
        trello_board_id = group['trello_board_id']
        id_viewers = []
        if group['_id'] != 'public':
          id_viewers.append(group['_id'])
        if id_viewers:
          api.notification_trello_queue.enqueue_call(func=get_notifications_trello, 
                                                     args=(trello_app_key, trello_token,
                                                            trello_board_id, id_viewers))
          
          
if __name__ == '__main__':
  while(True):
    push_notification_trello()
    time.sleep(3*60)
  
