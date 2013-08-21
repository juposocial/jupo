#! coding: utf-8
"""


Mail addresses:

 - post-{{ post.id }}
 - group-{{ group.id }}
 - user-{{ user.id }}

  - post-1234567890@reply.joomlart.jupo.com
"""

import api
import smaz
import smtpd
import base64
import asyncore
from lib.email_parser import get_reply_text
from lib.email_parser import get_subject  


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
    message = get_reply_text(data)
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
      group_slug = item_id[5:]
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
      
      api.new_comment(session_id, message, post_id, db_name=db_name)
      return None
    elif group_slug:
      #get user id based on email
      user_id = api.get_user_id_from_email_address(user_email, db_name='play_jupo_com')
      if not user_id:
        return None
      session_id = api.get_session_id(user_id, db_name='play_jupo_com')
      if not session_id:
        return None

      #get group id based on group slug
      group_id = api.get_group_id_from_group_slug(group_slug, db_name='play_jupo_com')
      if not group_id:
        return None

      #ensure the string is in Unicode
      if isinstance(message, str):
        try:
          message.decode('utf-8')
        except UnicodeDecodeError:
          message = message.decode('iso-8859-1', 'ignore').encode('utf-8')

      subject = header_raw[0][0]
      
      if isinstance(subject, str):
        try:
          print "DEBUG - subject = " + subject.encode('utf-8')
          subject.decode('utf-8')
        except UnicodeDecodeError:
          subject = subject.decode('iso-8859-1', 'ignore').encode('utf-8')

      #insert subject into message
      message = "<b>"> + subject + "</b>" + "\n" + message
      #post to group, no attachment for now
      api.new_feed(session_id, message, [group_id], attachments=None, facebook_access_token=None)

    else:
      return None
    

if __name__ == '__main__':
  server = JupoSMTPServer(('0.0.0.0', 25), None)
  asyncore.loop()
  
  
  