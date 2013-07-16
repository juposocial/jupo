# ! coding: utf-8
import urllib
import json
import httplib
import urllib2
import requests
import sys
import re
import api
TRELLO_APP_KEY = '950ba9d46c41d2bf9de1e89b57df68ca'
ID_BOARDS_JUPO = '51d6377f4b4cbf2f3f004068'
TOKEN = '3dfd9ea21d521b3f019d9d1757cf4bc95f0044c12e9ac9af7ada1cafe6937a0d'
URL_DATA = 'https://trello.com/1/boards/51d6377f4b4cbf2f3f004068?actions=all&actions_limit=20&key=%s&token%s' \
                % (TRELLO_APP_KEY,TOKEN)

# group jupo dev
ID_VIEWERS = [438236081108811777]

# group test_trello
# ID_VIEWERS = [481392403568132097]
# ID_VIEWERS = ['public']


LENG_LIST_ID_IN_FILE = 20

DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
EMAIL_JUPO = 'trello@yahoo.com'
PASS_JUPO = 'thieuchuthieuchu'

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


def remove_id_from_file():
  f = open('list_id_notification.txt','r+')
  list_id_info = f.read()
  list_id = list_id_info.split(' ')
  if len(list_id) > LENG_LIST_ID_IN_FILE:
    buf_list_id = list_id[len(list_id) - LENG_LIST_ID_IN_FILE - 1:]
    buf_str = ' '.join(str(i) for i in buf_list_id)
    f.truncate()
    f.close()
    f = open('list_id_notification.txt','w')
    f.write(buf_str)
  f.close()

  
def get_notifications():
  data = urllib.urlopen(URL_DATA).read()
  data = json.loads(data)
  f = open('list_id_notification.txt','r+')
  list_id_info = f.read()
  list_id = []
  try:
    list_id = list_id_info.split(' ')
  except:
    pass
  list_message = []
  for i in range(0,len(data['actions']) - 1):
    data_action = data['actions'][i]
    
    if data_action['id'] not in list_id:
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
      f.write(data_action['id'] + ' ')
  f.close()
  
  # UPDATE them truong id_card_trello toi id_post_message
  # moi commend.type ma la kieu comment thi tim feed
  for info_card in reversed(list_message):
    if info_card['type'] != 'commentCard':
      id_post_message = api.post_message_trello('trello', info_card['message'], ID_VIEWERS)
      if id_post_message:
        api.add_id_trello_to_stream(id_post_message, info_card['id'])
    else:
      api.comment_message_trello(info_card['message'], info_card['id'])
    
  remove_id_from_file()


if __name__ == '__main__':
  get_notifications()