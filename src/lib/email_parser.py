#! coding: utf-8

from email_reply_parser import EmailReplyParser as reply_parser_1

import re
import email

import lxml.html
import htmlentitydefs
from pyquery import PyQuery

def get_subject(data):
  msg = email.message_from_string(data)
  return msg['Subject']

def get_reply_and_original_text(data):
  """
  Strip signatures and replies from emails
  http://stackoverflow.com/a/2193937
  
  Drop all text after and including:

  Lines that equal '-- \n' (standard email sig delimiter)
  Lines that equal '--\n' (people often forget the space in sig delimiter; and this is not that common outside sigs)
  Lines that begin with '________________________________' (32 underscores, Outlook agian)
  Lines that begin with 'On ' and end with ' wrote:\n' (OS X Mail.app default)
  Lines that begin with 'From: ' (failsafe four Outlook and some other reply formats)
  Lines that begin with 'Sent from my iPhone'
  Lines that begin with 'Sent from my BlackBerry'
  """
  msg = email.message_from_string(data)
  msg_type = None
  if msg.get_content_maintype() == 'text':
    message = msg.get_payload(decode=True)
  elif msg.get_content_maintype() == 'multipart': #If message is multi part we only want the text version of the body, this walks the message and gets the body.
    for part in msg.walk():       
      if part.get_content_type() == "text/plain":
        message = part.get_payload(decode=True)
        break
      elif part.get_content_type() == "text/html":
        message = part.get_payload(decode=True)
        msg_type = 'text/html'
        break
      else:
        continue
  else:
    return False, msg_type
  
  msg = message.split('-- \n', 1)[0]
  msg = msg.split('--\n', 1)[0]
  
  lines = msg.split("\n")
  message_lines = []
  for line in lines:
    if line.startswith('-----Original Message-----'):
      break
    elif line.startswith('________________________________'):
      break
    elif line.startswith('On ') and line.endswith(' wrote:\n'):
      break
    elif line.startswith('From: '):
      break
    elif line.startswith('Sent from '):
      break
    
    # Trường hợp dạng: 2013/1/16 Pham Tuan Anh <anhpt@5works.co> (Gmail)
    elif re.match('[0-9]{4}/[0-9]?[0-2]/[0-9]?[0-9] .*? <\w+@\w+\.\w+>', line):
      break
    else:
      message_lines.append(line)
      
  msg = '\n'.join(message_lines)

  msg = reply_parser_1.parse_reply(msg)
  return msg.strip(), msg_type

def unescape(text):
  def fixup(m):
    text = m.group(0)
    if text[:2] == "&#":
      # character reference
      try:
        if text[:3] == "&#x":
          return unichr(int(text[3:-1], 16))
        else:
          return unichr(int(text[2:-1]))
      except ValueError:
        pass
    else:
      # named entity
      try:
        text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
      except KeyError:
        pass
    return text # leave as is
  return re.sub("&#?\w+;", fixup, text)

def fix_unclosed_tags(html):
  if not html:
    return html

  try:
    html = unicode(html)
  except UnicodeDecodeError:
    pass

  h = lxml.html.fromstring(html)
  out = lxml.html.tostring(h)
  return unescape(out)

def get_text(html):
  print "DEBUG - in email_parser - get_text - html = " + str(html)
  """
  Strip signatures and replies from emails
  """

  separators = [
    '<div class="gmail_extra">',
    'class="moz-signature"',
    '<div class="gmail_quote">',
    '<div><br></div><div>--&nbsp;</div>',
    '<div>--&nbsp;</div>',
    '<div>-- <br>',
    '<div><br></div>-- </div>',
    '-- <br>',
    '>---<br>',
    '<br clear="all"><div><div><br></div>'
  ]
  for separator in separators:
    if separator in html:
      print separator
      html = html.split(separator, 1)[0]

  if 'MsoNormal' in html:
    if "From:" in html:
      html = html.split('>From:</', 1)[0]
    if ';border-top:solid' in html:
      html = html.split(';border-top:solid', 1)[0]
  lines = []
  for line in html.split('\n'):
    if '<br>' in line:
      lines.extend([i + '<br>' for i in line.split('<br>')])
    elif '<br/>' in line:
      lines.extend([i + '<br/>' for i in line.split('<br/>')])
    elif '<br />' in line:
      lines.extend([i + '<br />' for i in line.split('<br />')])
    elif '</p>' in line:
      lines.extend([i + '</p>' for i in line.split('</p>')])
    else:
      lines.append(line)
  print 'lines ', lines

  message_lines = []
#   lines = ['---------- Forwarded message ----------' , 'test gui email ko subject', '']
  for line in lines:
    if 'Forwarded message' in line:
      pass
    elif '-----Original Message-----' in line:
      pass
    elif 'Date:' in line:
      pass
    elif 'To:' in line:
      pass
    elif 'Fwd:' in line:
      pass
    elif 'Subject: Fwd' in line:
      pass
    elif 'Subject:' == line:
      pass
    elif '________________________________' in line:
      pass
    elif '---------------------' in line:
      pass
    elif '>---<br>' in line:  # Outlook
      pass
    elif 'From:' in line:
      pass
    elif 'best regards' in line.lower():
      pass
    elif 'Sent from ' in line:
      pass
    elif re.findall("On .*?, .*? wrote:", line):
      pass
    elif re.findall('[0-9]{4}/\d+/\d+ .*? <\w+@\w+\.\w+>', line):
      pass
    else:
      message_lines.append(line)
  html = '\n'.join(message_lines)
  if 'MsoNormal' in html:
    doc = PyQuery(html)
    doc('head').remove()
    doc('.MsoNormal span[style]').attr('style', None)
    doc('.MsoListParagraph[style]').attr('style', None)
    return doc.html().replace('<p> </p>', '')
  else:
    html = fix_unclosed_tags(html.strip())
    return html

def get_reply_text(data):
  """
  Strip signatures and replies from emails
  http://stackoverflow.com/a/2193937

  Drop all text after and including:

  Lines that equal '-- \n' (standard email sig delimiter)
  Lines that equal '--\n' (people often forget the space in sig delimiter; and this is not that common outside sigs)
  Lines that begin with '-----Original Message-----' (MS Outlook default)
  Lines that begin with '________________________________' (32 underscores, Outlook agian)
  Lines that begin with 'On ' and end with ' wrote:\n' (OS X Mail.app default)
  Lines that begin with 'From: ' (failsafe four Outlook and some other reply formats)
  Lines that begin with 'Sent from my iPhone'
  Lines that begin with 'Sent from my BlackBerry'
  """

  msg = email.message_from_string(data)
  print "DEBUG - in email_parser - get_reply_text - msg = " + str(msg)
  msg_type = None
  message_plain_text = None
  message_html = None
  if msg.get_content_maintype() == 'text':
    message = msg.get_payload(decode=True)
  elif msg.get_content_maintype() == 'multipart': #If message is multi part we only want the text version of the body, this walks the message and gets the body.
    for part in msg.walk():
      if part.get_content_type() == "text/plain":
        message_plain_text = part.get_payload(decode=True)
      elif part.get_content_type() == 'text/html':
        message_html = part.get_payload(decode=True)
      else:
        continue
  else:
    return False, msg_type

  message_plain_text = get_text(message_plain_text).strip()

  if message_plain_text and message_html:
    if len(message_plain_text) < 500:
      message = message_plain_text
    else:
      message = message_html
      msg_type = 'text/html'

  msg = message.split('-- \n', 1)[0]
  msg = msg.split('--\n', 1)[0]

  lines = msg.split("\n")
  message_lines = []
  for line in lines:
    if line.startswith('-----Original Message-----'):
      break
    elif line.startswith('________________________________'):
      break
    elif line.startswith('On ') and line.endswith(' wrote:\n'):
      break
    elif line.startswith('From: '):
      break
    elif line.startswith('Sent from '):
      break

    # Trường hợp dạng: 2013/1/16 Pham Tuan Anh <anhpt@5works.co> (Gmail)
    elif re.match('[0-9]{4}/[0-9]?[0-2]/[0-9]?[0-9] .*? <\w+@\w+\.\w+>', line):
      break
    else:
      message_lines.append(line)

  msg = '\n'.join(message_lines)

  msg = reply_parser_1.parse_reply(msg)
  return msg.strip(), msg_type

if __name__ == '__main__':
  data = '''Return-Path: <anhpt@5works.co>
Received: from [192.168.1.145] ([123.16.115.26])
        by mx.google.com with ESMTPS id ky17sm9297970pab.23.2013.03.23.21.24.35
        (version=TLSv1 cipher=RC4-SHA bits=128/128);
        Sat, 23 Mar 2013 21:24:36 -0700 (PDT)
Date: Sun, 24 Mar 2013 11:24:31 +0700
From: "=?utf-8?Q?Tu=E1=BA=A5n_Anh_-_5works.co?=" <anhpt@5works.co>
To: post-123456@jupo.com
Message-ID: <64E928A8DBFD4E08927478369533F3AC@5works.co>
In-Reply-To: <10786563.20130324042324.514e7fbc01fa62.82280722@mail316.us4.mandrillapp.com>
References: <10786563.20130324042324.514e7fbc01fa62.82280722@mail316.us4.mandrillapp.com>
Subject: Re: test
X-Mailer: sparrow 1.6.4 (build 1176)
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="514e7fff_12e685fb_b7"

--514e7fff_12e685fb_b7
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: quoted-printable
Content-Disposition: inline

Reply coment via email =20

-- =20
Tu=E1=BA=A5n Anh - 5works.co
Sent with Sparrow (http://www.sparrowmailapp.com/=3Fsig)


On Sunday, March 24, 2013 at 11:23am, Jupo Team wrote:

> =46oo
> =20



--514e7fff_12e685fb_b7
Content-Type: text/html; charset="utf-8"
Content-Transfer-Encoding: quoted-printable
Content-Disposition: inline


                <div>Reply coment via email
                </div>
                <div><div><br></div><div>--&nbsp;</div><div>Tu=E1=BA=A5n =
Anh - 5works.co</div><div>Sent with <a href=3D=22http://www.sparrowmailap=
p.com/=3Fsig=22>Sparrow</a></div><div><br></div></div>
                =20
                <p style=3D=22color: =23A0A0A8;=22>On Sunday, March 24, 2=
013 at 11:23am, Jupo Team wrote:</p>
                <blockquote type=3D=22cite=22 style=3D=22border-left-styl=
e:solid;border-width:1px;margin-left:0px;padding-left:10px;=22>
                    <span><div><div>=46oo<img src=3D=22http://mandrillapp=
.com/track/open.php=3Fu=3D10786563&amp;id=3D47786c48ff47487eb5dc86ae7b11a=
445&amp;tags=3D=5Fall,=5Fsendhello=40jupo.com=22 height=3D=221=22 width=3D=
=221=22></div></div></span>
                =20
                =20
                =20
                =20
                </blockquote>
                =20
                <div>
                    <br>
                </div>
            
--514e7fff_12e685fb_b7--

'''
  print get_reply_text(data)  