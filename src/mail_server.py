#! coding: utf-8
"""


Mail addresses:

 - post-{{ post.id }}
 - group-{{ group.id }}
 - user-{{ user.id }}

  - post-1234567890@reply.joomlart.jupo.com
"""

import api
import re
import smaz
import smtpd
import base64
import email
import asyncore
from lib.email_parser import get_reply_text
from lib.email_parser import get_reply_and_original_text
from lib.email_parser import get_subject  
import settings

class JupoSMTPServer(smtpd.SMTPServer):
  def process_message(self, peer, mailfrom, rcpttos, data):
    """
    peer is a tuple containing (ipaddr, port) of the client that made the
    socket connection to our smtp port.

    mailfrom is the raw address the client claims the message is coming
    from.

    rcpttos is a list of raw addresses the client wishes to deliver the
    message to.

    data is a string containing the entire full text of the message,
    headers (if supplied) and all.  It has been `de-transparencied'
    according to RFC 821, Section 4.5.2.  In other words, a line
    containing a `.' followed by other text has had the leading dot
    removed.

    This function should return None, for a normal `250 Ok' response;
    otherwise it returns the desired response string in RFC 821 format.

    """
    print peer, mailfrom, rcpttos, len(data)
    
    user_email = mailfrom.lower().strip()
    # Extract reply text from message
    message, type_message = get_reply_text(data)
    subject = get_subject(data)
    header_raw = email.header.decode_header(subject)
    
    
    if not message:
      return None # Can't parse reply text
    
    item_id = rcpttos[0].split('@')[0]
    post_id = user_id = group_id = None
    if item_id.startswith('post'):
      post_id = item_id[4:]
    elif item_id.startswith('user'):
      user_id = item_id[4:]
    elif item_id.startswith('group'):
      network_group_slug = item_id[6:]
      network_slug, group_slug = network_group_slug.split['.']
    else:
      return None
    
    if post_id:
      post_id = post_id.replace('-', '/')
      while True:
        try:
          post_id = smaz.decompress(base64.b64decode(post_id))
          break
        except TypeError: # Incorrect padding
          post_id = post_id + '='
      post_id, db_name = post_id.split('-')
      if not post_id.isdigit():
        return None
      
      post_id = int(post_id)
      user_id = api.get_user_id_from_email_address(user_email, db_name=db_name)
      if not user_id:
        return None
      session_id = api.get_session_id(user_id, db_name=db_name)
      if not session_id:
        return None
      if type_message:
        api.new_comment(session_id, 'Please click view to see more', post_id, db_name=db_name, html=message)
      else:
        api.new_comment(session_id, message, post_id, db_name=db_name)
      return None
    elif group_slug:
      # post from email
      hostname = mailfrom.split('@')[1]

      # construct db_name from network slug + PRIMARY_DOMAIN
      db_name = network_slug.replace('-', '.') + '.' + settings.PRIMARY_DOMAIN
      # db_name = hostname.replace('.', '_') + '_jupo_com'

      # message, type_message = get_reply_and_original_text(data)
      
      # get user id based on email
      user_id = api.get_user_id_from_email_address(user_email, db_name=db_name)
      if not user_id:
        return None
      session_id = api.get_session_id(user_id, db_name=db_name)
      if not session_id:
        return None

      # get group id based on group slug
      group_id = api.get_group_id_from_group_slug(group_slug, db_name=db_name)
      if not group_id:
        return None

      # ensure the string is in Unicode
      if isinstance(message, str):
        try:
          message.decode('utf-8')
        except UnicodeDecodeError:
          message = message.decode('iso-8859-1', 'ignore').encode('utf-8')

      subject = header_raw[0][0]
      
      if isinstance(subject, str):
        try:
          # print "DEBUG - subject = " + subject.encode('utf-8')
          subject.decode('utf-8')
        except UnicodeDecodeError:
          subject = subject.decode('iso-8859-1', 'ignore').encode('utf-8')

      #insert subject into message
      if type_message is None:
        message = "<b>" + subject + "</b>" + "\n" + message
        
      # check for mention in message/subject
      # SO: http://stackoverflow.com/questions/2304632/regex-for-twitter-username
      target = []
      mentioned_found = re.findall('(?<=^|(?<=[^a-zA-Z0-9-_\.]))@([A-Za-z]+[A-Za-z0-9]+)', message)
      #print "DEBUG - mail_server.py - qty mentioned_found = " + len(mentioned_found.group)

      if len(mentioned_found) > 0:
        for record in mentioned_found:
          nickname = str(record)
          # print "DEBUG - mail_server.py - mentioned_found = " + nickname
          # print "DEBUG - mail_server.py - user_id = " + str(api.get_user_id_from_nickname(nickname[1:]))

          if api.get_user_id_from_nickname(nickname[1:]) is not None:
            target.append(api.get_user_id_from_nickname(nickname[1:]))

      target.append(group_id)

      #post to group, no attachment for now
      if type_message is None:
        api.new_feed(session_id, message, target, 
                     attachments=None, facebook_access_token=None, 
                     db_name=db_name)
        
      else:
        api.new_feed(session_id, subject, target, 
                     attachments=None, facebook_access_token=None, 
                     html=message, db_name=db_name)
    else:
      return None
    
    
if __name__ == '__main__':
  server = JupoSMTPServer(('0.0.0.0', 25), None)
  asyncore.loop()