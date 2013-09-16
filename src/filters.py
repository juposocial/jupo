#! coding: utf-8
# pylint: disable-msg=W0311, E0611, E1103, E1101
#@PydevCodeAnalysisIgnore
import re
import api
import textwrap
import calendar
import lxml.html
from hashlib import md5
from string import capwords
from pyquery import PyQuery
from urlparse import urljoin 
from simplejson import loads
from datetime import datetime
from lib import cache
from markdown2 import markdown
from lib.wordunmunger import unmungeHtml
from BeautifulSoup import BeautifulSoup, Tag, NavigableString, Comment
from flask_debugtoolbar_lineprofilerpanel.profile import line_profile

from lib import emoji

months = dict((k,v) for k,v in enumerate(calendar.month_abbr)) 


def last_starred_user(following_users, starred_list):
  user_ids = set([u for u in following_users]).intersection(set(starred_list))
  if user_ids:
    user_id = list(user_ids)[-1]
    return api.get_user_info(user_id)

@line_profile
def lines_truncate(text, lines_count=5):
  
#   key = '%s:lines_truncate' % hash(text)
#   out = cache.get(key, namespace="filters")
#   if out:
#     return out
  
  raw = text
  text = _normalize_newlines(text)
  is_html = True if ('<br>' in raw or '</' in raw) else False
  
  # remove blank lines
  if is_html:
    
    images = re.compile('<img.*?>', re.IGNORECASE).findall(text)
    for i in images:
      text = text.replace(i, md5(i).hexdigest())
    
    links = re.compile('<a.*?</a>', re.IGNORECASE).findall(text)
    for i in links:
      text = text.replace(i, md5(i).hexdigest())
      
    text = text.replace('<br/>', '<br>')
    
    lines = [line for line in text.split('<br>') if line.strip()]
    
  else:
    lines = [line for line in text.split('\n') if line.strip()]
    text = text.strip().replace('\n', '<br>')
  
  words_per_line = 15
  longest_line = max(lines[:lines_count], key=len) if len(lines) != 0 else None
  if longest_line and len(longest_line.split()) > words_per_line: 
    lines = textwrap.wrap(text)
  else:
    lines = [line for line in text.split('<br>') if line.strip()]
    
  # skip blank lines (and blank lines quote)
  if len([line for line in lines if line.strip() and line.strip() != '>']) >= lines_count:
    blank_lines = len([line for line in text.split('<br>') if line.strip() in ['', '>']])
    out = '<br>'.join(lines[:lines_count+blank_lines])
  else:
    out = text
    
  is_truncated = False
  if len(out) < len(text):
    lines = text[:len(out)].split('<br>')
    if len(lines) > 1:
      text = '<br>'.join(lines[0:-1]).rstrip('.')
        
    is_truncated = True
    
    if len(text) / float(len(raw)) > 0.7: # nếu còn 1 ít text thì hiện luôn, không cắt làm gì cho mệt
      text = raw
      is_truncated = False
  
  if not is_html:
    out = text.replace('<br>', '\n')
  
  if is_html:
    for i in images:
      out = out.replace(md5(i).hexdigest(), i)
    for i in links:
      out = out.replace(md5(i).hexdigest(), i)
    
    if is_truncated and not out.rstrip().endswith('...</a>'):
      out = out + '...'
    
#   cache.set(key, out, namespace="filters")
  return out  


@line_profile
def nl2br(value):
  # Giữ các ký tự <br> hoặc \n là text
  value = value.replace('<br>', '8b0f0ea73162b7552dda3c149b6c045d')
  value = value.replace('"\n"', '2ab3d62a4a147cea43e1e37ba39fa124')
  value = value.replace("'\n'", 'e757d0808bdc16a9047ee997fb8e4d80')
  
  lines = value.split('\n')
  
  # giữ khoảng trắng đầu dòng
  out = []
  for line in lines:
    if line.strip():
      chars = list(line)
      i = 0
      for c in chars:
        if c != ' ':
          break
        i += 1
      line = line.replace(' ', '&nbsp;', i)
    out.append(line)
  
  value = '<br>'.join(out)
  return value.replace('8b0f0ea73162b7552dda3c149b6c045d', '<br>')\
              .replace('2ab3d62a4a147cea43e1e37ba39fa124', '"\n"')\
              .replace('e757d0808bdc16a9047ee997fb8e4d80', "'\n'")


def symbols(text):
  map = {'(c)'  : '©', 
         '(r)'  : '®', 
         '(tm)' : '™',
         '<3'   : '♥'}
  for s in map.keys():
    text = text.replace(s, map[s])
  return text


def parse_json(text):
  try:
    text = text.strip()
    # gitlab quên không escape ký tự nháy kép (") trong commit message
    messages = re.findall('message":"(.*?)",', text)
    messages = [m for m in messages if m.count('"') != 0]
    for m in messages:
      m2 = m.replace('\\"', '`')
      text = text.replace(m, m2)
    text = loads(text)
    return text
  except Exception:
    return None

EMAIL_RE = re.compile('^[_a-zA-Z0-9-]+(\.[_a-zA-Z0-9-]+)*@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*(\.[a-zA-Z]{2,4})$')
MENTIONS_RE = re.compile('(@\[.*?\]\(.*?\))')

@line_profile
def autolink(text):  
  if not text:
    return text
  
  key = '%s:autolink' % hash(text)
  out = cache.get(key, namespace="filters")
  if out:
    return out
  
  if re.match(EMAIL_RE, text):
    email = text 
    user_id = api.get_user_id_from_email_address(email)
    user = api.get_user_info(user_id)
    return '<a href="/user/%s" class="async">%s</a>' % (user.id, user.name)
    
  s = text or ''
  s += ' '
  s = str(s) # convert unicode to string
  s = s.replace('\r\n', '\n')

  try:
    urls = api.extract_urls(s)
  except Exception:
    urls = []
  urls = list(set(urls))
  urls.sort(key=len, reverse=True)
  
  for url in urls:
    hash_string = md5(url).hexdigest()
    info = api.get_url_info(url)
    if not url.startswith('http'):
      s = s.replace(url, '<a href="http://%s/" target="_blank" title="%s">%s</a>' % (hash_string, info.title if info.title else hash_string, hash_string))
    
    elif len(url) > 60:
      u = url[:60]
        
      for template in ['%s ', ' %s', '\n%s', '%s\n', '%s.', '%s,']:
        if template % url in s:
          s = s.replace(template % url, 
                        template % ('<a href="%s" target="_blank" title="%s">%s</a>' % (hash_string, info.title if info.title else hash_string, md5(u + '...').hexdigest())))
          break
    else:
      for template in ['%s ', ' %s', '\n%s', '%s\n', '%s.', '%s,']:
        if template % url in s:
          s = s.replace(template % url, 
                        template % ('<a href="%s" target="_blank" title="%s">%s</a>' % (hash_string, info.title if info.title else hash_string, hash_string)))
          break
        
  for url in urls:
    s = s.replace(md5(url).hexdigest(), url)
    if len(url) > 60 and url.startswith('http'):
      s = s.replace(md5(url[:60] + '...').hexdigest(), url[:60] + '...')
      
  
  mentions = MENTIONS_RE.findall(s)
  if mentions:
    for mention in mentions:
      if '](topic:' in mention:
        parts = mention.split("](topic:")
        topic_id = parts[1][:-1]
        topic_name = parts[0][2:]
        
        #TODO: update topic name?
        s = s.replace(mention, 
             '<a href="/chat/topic/%s" class="chat">%s</a>' % (topic_id, topic_name))
      elif '](user:' in mention:
        parts = mention.split("](user:")
        user_id = parts[1][:-1]
        username = parts[0][2:]
        s = s.replace(mention, 
             '<a href="/user/%s" class="async"><span class="tag">%s</span></a>' % (user_id, username))
      elif '](group:' in mention:
        parts = mention.split("](group:")
        group_id = parts[1][:-1]
        group_name = parts[0][2:]
        s = s.replace(mention, 
             '<a href="/group/%s" class="async"><span class="tag">%s</span></a>' % (group_id, group_name))
      elif '](dropbox-file:' in mention:
        
        parts = mention.split("](dropbox-file:")
        link = parts[1][:-1].replace('www.dropbox.com', 'dl.dropboxusercontent.com', 1)
        name = parts[0][2:]
        s = s.replace(mention,
                      '<a href="%s" target="_blank">%s</a>' % (link, name))
      elif '](google-drive-file:' in mention:
        
        parts = mention.split("](google-drive-file:")
        link = parts[1][:-1]
        name = parts[0][2:]
        s = s.replace(mention,
                      '<a href="%s" target="_blank">%s</a>' % (link, name))
        
      else:
        continue
        
#  hashtags = re.compile('(#\[.*?\))').findall(s)
#  if hashtags:
#    for hashtag in hashtags:
#      tag = re.compile('#\[(?P<name>.+)\]\((?P<id>.*)\)').match(hashtag).groupdict()
#      tag['id'] = tag['id'].split(':', 1)[-1]
#      s = s.replace(hashtag, 
#           '<a href="?hashtag=%s" class="overlay"><span class="tag">%s</span></a>' % (tag.get('id'), tag.get('name')))
  
  cache.set(key, s, namespace="filters")
  return s


def unescape(s):
  s = s.replace("&lt;", "<")
  s = s.replace("&gt;", ">")
  s = s.replace("&amp;", "&") # last
  return s

REFERENCE_URL_REGEX = re.compile(r"""\n(\[[a-zA-Z0-9_-]*\]: (?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])))""")
  
def flavored_markdown(text): 
  key = '%s:flavored_markdown' % hash(text)
  html = cache.get(key, namespace="filters")
  if html:
    return html
   
  text = ' ' + text + ' '
  text = unescape(text)
  
  # extract Reference-style links
  reference_urls = REFERENCE_URL_REGEX.findall(text)
  reference_urls = [i[0] for i in reference_urls]
  for i in reference_urls:
    text = text.replace(i, md5(i).hexdigest())  
  
  # extract urls
  urls = URL_REGEX.findall(text)
  urls = [i[0] for i in urls if i]
  urls.sort(key=len, reverse=True)
  for url in urls:
    for pattern in ['%s)', ' %s', '\n%s', '\r\n%s', '%s\n', '%s\r\n']:
      if pattern % url in text:
        text = text.replace(pattern % url, pattern % md5(url).hexdigest())
        break
      
  # extract emoticons and symbols
  symbols = EMOTICONS.keys()
  symbols.extend(SYMBOLS.keys())
  symbols.sort(key=len, reverse=True)
  for symbol in symbols:
    for pattern in [' %s', ' %s. ', ' %s.\n', ' %s.\r\n', '\n%s', '\r\n%s', '%s\n', '%s\r\n']:
      if pattern % symbol in text:
        text = text.replace(pattern % symbol, pattern % md5(symbol).hexdigest())
        break
  
  # extract mentions
  mentions = re.findall('(@\[.*?\))', text)
  if mentions:
    for mention in mentions:
      text = text.replace(mention, md5(mention).hexdigest())
  
  # extract hashtags
  hashtags = re.findall('(#\[.*?\))', text)
  if hashtags:
    for hashtag in hashtags:
      text = text.replace(hashtag, md5(hashtag).hexdigest())
            
  # extract underscores words - prevent foo_bar_baz from ending up with an italic word in the middle
  words_with_underscores = [w for w in \
                            re.findall('((?! {4}|\t)\w+_\w+_\w[\w_]*)', text) \
                            if not w.startswith('_')]
  
  for word in words_with_underscores:
    text = text.replace(word, md5(word).hexdigest())
  
  # treats newlines in paragraph-like content as real line breaks
  text = text.strip().replace('<br>', '8b0f0ea73162b7552dda3c149b6c045d')
  text = text.strip().replace('\r\n', '<br>').replace('\n', '<br>') # normalize \r\n and \n to <br>
  text = text.strip().replace('<br>', '  \n') # treats newlines
  text = text.strip().replace('||  \n', '||\n') # undo if wiki-tables
  text = text.strip().replace('8b0f0ea73162b7552dda3c149b6c045d', '<br>')
  
  # restore reference_urls
  for i in reference_urls:
    text = text.replace(md5(i).hexdigest(), i) 
  
  # convert text to html
  html = markdown(text, extras=["wiki-tables",
                                "cuddled-lists",
                                "fenced-code-blocks",
                                "header-ids",
                                "code-friendly",
                                "pyshell",
                                "footnotes"])
  
#  print html
  
  # extract code-blocks
  html = html.replace('\n', '<br/>') # convert multi-lines to single-lines for regex matching
  code_blocks = re.findall('(<code>.*?</code>)', html)
  for block in code_blocks:
    html = html.replace(block, md5(block).hexdigest())
    
    
  # Show emoticons and symbols
  for symbol in symbols:
    if SYMBOLS.has_key(symbol):
      html = html.replace(md5(symbol).hexdigest(),
                          SYMBOLS[symbol])
    else:
      html = html.replace(md5(symbol).hexdigest(),
                          EMOTICONS[symbol].replace("<img src", 
                                                    "<img class='emoticon' src"))
  
  # Autolinks urls, mentions, hashtags, turn youtube links to embed code
  for url in urls: 
    title = api.get_url_info(url).title
    hash_string = md5(url).hexdigest()
    if len(url) > 40:
      html = html.replace(hash_string, 
                          '<a href="%s" target="_blank" title="%s">%s</a>' % (url, title, url[:40] + '...'))
    else:
      html = html.replace(hash_string, 
                          '<a href="%s" target="_blank" title="%s">%s</a>' % (url, title, url))
  
  for mention in mentions:
        
    hash_string = md5(mention).hexdigest()
    
    
    parts = mention.split("](user:")
    username = parts[0][2:]
    user_id = parts[1][:-1]
    html = html.replace(hash_string, 
                        '<a href="/user/%s" class="async"><span class="tag">%s</span></a>' % (user_id, username))
  
#   for hashtag in hashtags:
#     hash_string = md5(hashtag).hexdigest()
#     tag = re.compile('#\[(?P<name>.+)\]\((?P<id>.*)\)').match(hashtag).groupdict()
#     tag['id'] = tag['id'].split(':', 1)[-1]
#     html = html.replace(hash_string, 
#                         '<a href="?hashtag=%s" class="overlay"><span class="tag">%s</span></a>' % (tag.get('id'), tag.get('name')))  
    
  # Restore code blocks
  for block in code_blocks:
    html = html.replace(md5(block).hexdigest(), block)
  
  # restore urls, mentions, emoticons and hashtag in code blocks
  for url in urls:
    html = html.replace(md5(url).hexdigest(), url)
  for mention in mentions:
    html = html.replace(md5(mention).hexdigest(), mention)
  for hashtag in hashtags:
    html = html.replace(md5(hashtag).hexdigest(), hashtag)  
  for symbol in symbols:
    html = html.replace(md5(symbol).hexdigest(), symbol)  
  
  # restore words with underscores
  for word in words_with_underscores:
    html = html.replace(md5(word).hexdigest(), word)
  
  # restore \n
  html = html.replace('<br/>', '\n') 

  # xss protection
  html = sanitize_html(html)

  if not html or html.isspace():
    return ''
  
  
  # add target="_blank" to all a tags
  html = PyQuery(html)
  html('a:not(.overlay)').attr('target', '_blank')
  html = str(html)
  html = html.replace('<br/>', '<br>')
  
  cache.set(key, html, namespace="filters")
  return html  
  
@line_profile
def to_embed_code(url, width=437, height=246): 
  youtube_embed_code_template = '<iframe width="%s" height="%s" src="https://www.youtube.com/embed/%s?wmode=opaque" frameborder="0" allowfullscreen></iframe>'
  if not url.startswith('http'):
    urls = api.extract_urls(url)
    if urls:
      url = urls[0]
  
  if 'www.youtube.com/' in url:      
    video_id = url.rsplit('?v=', 1)[-1].split('&', 1)[0]
    embed_code = youtube_embed_code_template % (width, height, video_id)
    
  elif 'youtu.be/' in url:    
    video_id = url.rsplit('/', 1)[-1].split('&', 1)[0]
    embed_code = youtube_embed_code_template % (width, height, video_id)
  else:
    embed_code = ''
    
  return embed_code 
  

@line_profile
def autoemoticon(text):
  return emoji.emoji(text)


def unique_by_timestamp(text):
  text = '%s-%s' % (text, api.utctime())
  return md5(text).hexdigest()


def endswith(text, s):
  if text.strip().endswith(s):
    return True
  
  
def remove_groups(owners):
  return [x for x in owners if not x.is_group()]


def strftime(ts, offset=None, time_format='%b %d %I:%M%p'):
  try:
    ts = float(ts)
  except TypeError:
    return ts
  
  if offset:
    ts = ts + int(offset)  
  
  text = datetime.fromtimestamp(int(ts)).strftime(time_format)
  return text.replace(' 0', ' ').replace('AM', 'am').replace('PM', 'pm')
                                                             

@line_profile
def friendly_format(ts, offset=None, short=False):
  try:
    ts = float(ts)
  except TypeError:
    return ts
  
  if offset:
    ts = ts + int(offset)
  
  if short:
    now = api.utctime()
    if offset:
      now = now + int(offset)
    
    now = datetime.fromtimestamp(now)
    
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

@line_profile
def isoformat(ts, offset=None, last_hour=True):
  try:
    ts = float(ts)
  except TypeError:
    return ts
  
  if offset:
    ts = ts + int(offset)
    
  if last_hour:
    now = api.utctime()
    if now - ts < 3600:
      ts = datetime.fromtimestamp(ts)
      return ts.isoformat()
    return ''
  else:
    ts = datetime.fromtimestamp(ts)
    return ts.isoformat()


@line_profile
def fix_unclosed_tags(html):
  if not html:
    return html
  
  try:
    html = unicode(html)
  except UnicodeDecodeError:
    pass
  try:
    key = '%s:fix_unclosed_tags' % hash(html)
    out = cache.get(key, namespace="filters")
    if out:
      return out
  
    h = lxml.html.fromstring(html)
    out = lxml.html.tostring(h)
    
    cache.set(key, out, namespace="filters")
    return out
  except Exception:
    return ''


def fix_unicode_error(text):
  try:
    text.decode('utf-8')
    return text
  except UnicodeDecodeError:
    return text.decode('latin-1').encode("utf-8")

_newlines_re = api.re.compile(r'(\r\n|\r|\r)')
def _normalize_newlines(string):
    return _newlines_re.sub('\n', string)

def remove_signature(text):
  text = _normalize_newlines(text)
  
  parts = text.split('\n\n--', 1)
  if len(parts) != 2:
    parts = text.split('<br><br>--', 1)
    if len(parts) != 2:
      parts = text.split('\n\n__')
      
    
  if len(parts) == 2:
    text = parts[0].strip()
    
  # remove blockquote
  lines = text.split('\n')
  count = 0
  for line in lines:
    if ('On ' in line and ' wrote:' in line) or 'regard' in str(line).lower():
      break
    count += 1
  lines = lines[:count]
  text = '\r\n'.join(lines)
  return text


@line_profile
def remove_empty_lines(html):
  key = '%s:remove_empty_lines' % hash(html)
  out = cache.get(key, namespace="filters")
  if out:
    return out
  
  if '</' in html:
    html = html.strip().replace('\n', '')
    soup = BeautifulSoup(html)
    lines = []
    if len(soup.contents) == 1:
      contents = soup.contents[0].contents
    else:
      contents = soup.contents
    for element in contents:
      if isinstance(element, Tag):
        if element.text:
          lines.append(str(element).strip())
        elif 'br' in str(element):
          lines.append('\n')
      elif isinstance(element, NavigableString):
        lines.append(str(element).strip())
    out = ''.join(lines).strip()
    while '\n\n' in out:
      out = out.replace('\n\n', '\n')
    out = out.replace('\n', '<br>')
  else:
    out = '\n'.join([line for line in html.split('\n') if line.strip()])
  cache.set(key, out, namespace="filters")
  return out


def exclude(users, user_id):
  return [user for user in users if str(user.id) != str(user_id)] if users else []

def title(text):
  return capwords(text.replace('_', ' '))


def split(s, sep):
  return s.split(sep)
  

@line_profile
def clean(text):
  if not text:
    return ''
  
  text = str(text)
  
#  key = '%s:clean' % hash(text)
#  out = cache.get(key, namespace="filters")
#  if out:
#    return out
  mentions = re.findall('(@\[.*?]\(.*?\))', text)
  if mentions:
    for mention in mentions:
      if '](topic:' in mention:
        parts = mention.split("](topic:")
        name = parts[0][2:]
      elif '](user:' in mention:
        parts = mention.split("](user:")
        name = parts[0][2:]
      elif '](dropbox-file:' in mention:
        parts = mention.split("](dropbox-file:")
        name = parts[0][2:]
      elif '](google-drive-file:' in mention:
        parts = mention.split("](google-drive-file:")
        name = parts[0][2:]
      else:
        parts = mention.split("](group:")
        name = parts[0][2:]
      
      text = text.replace(mention, name)
      
#  hashtags = re.compile('(#\[.*?\))').findall(text)
#  if hashtags:
#    for hashtag in hashtags:
#      tag = re.compile('#\[(?P<name>.+)\]\((?P<id>.*)\)').match(hashtag).groupdict()
#      tag['id'] = tag['id'].split(':', 1)[-1]
#      text = text.replace(hashtag, tag.get('name'))
      
#  # Clean h1..h6, quotes...
#  lines = []
#  for line in text.split('\r\n'):
#    line = line.strip()
#    chars = list(set(line))
#    if line and not line.startswith(':::') and '```' not in line:
#      if len(chars) == 1 and chars[0] in ['-', '=', '_']:
#        continue
#      lines.append(line.lstrip('#').lstrip('>').strip())
#    
#  text = '\r\n'.join(lines)
#  while '<br><br>' in text:
#    text = text.replace('<br><br>', '<br>')
#  
#  text = text.replace('<br clear="all">', '')
  
#  cache.set(key, text, namespace="filters")
  return text


def unmunge(html):
  """Clean up Word HTML"""
  if 'mso' in html: # remove outlook html style
    key = '%s:unmunge' % hash(html)
    out = cache.get(key, namespace="filters")
    if not out:
      html = re.sub(re.compile('p"mso.*?"'), 'p', html)
      html = re.sub(re.compile('( style=".*?")'), '', html)
      out = unmungeHtml(html.decode('utf-8'))
      cache.set(key, out, namespace="filters")
    return out
  return html


def to_text(html):
  try:
    html = unicode(html)
  except UnicodeDecodeError:
    pass
  key = '%s:to_text' % hash(html)
  out = cache.get(key, namespace="filters")
  if not out:
    out = api.remove_html_tags(html)
    cache.set(key, out, namespace="filters")
  return out

def _convert_to_text(html):
  try:
    html = unicode(html)
  except UnicodeDecodeError:
    pass
  key = '%s:convert_to_text' % hash(html)
  out = cache.get(key, namespace="filters")
  if not out:
    html = fix_unclosed_tags(html)
    plain_text = api.remove_html_tags(html)
    cache.set(key, out, namespace="filters")
  return out
  
  
def description(html):
  try:
    html = unicode(html)
  except UnicodeDecodeError:
    pass
  key = '%s:description' % hash(html)
  out = cache.get(key, namespace="filters")
  if out:
    return out
  
  if '</' in html:
    plain_text = _convert_to_text(html)
  else:
    plain_text = html
  lines = []
  for line in plain_text.split('\n'):
    if '(' in line or ')' in line:
      continue
    elif '[' in line or ']' in line:
      continue
    elif '/' in line:
      continue
    elif ';' in line:
      continue
    elif ' ' in line \
      and len(line) > 15 \
      and line.count('.') < 2 \
      and 'dear' not in line.lower() \
      and 'hi' not in line.lower() \
      and 'unsubscribe' not in line.lower():
      lines.append(clean(line))
    else:
      continue
  
  lines.sort(key=len)
  if lines:
    out = lines[-1].rstrip('.') + '...'
  else:
    out = '...'
  cache.set(key, out, namespace="filters")
  return out
  
  
@line_profile
def sanitize_html(value):
  '''
  https://stackoverflow.com/questions/16861/sanitising-user-input-using-python
  '''
  if '</' not in value: # không phải HTML
    return value
  
  key = '%s:sanitize_html' % hash(value)
  out = cache.get(key, namespace="filters")
  if out:
    return out
  
  base_url=None
  rjs = r'[\s]*(&#x.{1,7})?'.join(list('javascript:'))
  rvb = r'[\s]*(&#x.{1,7})?'.join(list('vbscript:'))
  re_scripts = re.compile('(%s)|(%s)' % (rjs, rvb), re.IGNORECASE)
#  validTags = 'p i strong b u a h1 h2 h3 h4 pre br img ul ol li blockquote em code hr'.split()
  validTags = 'a abbr b blockquote code del ins dd dl dt em h2 h3 h4 i img kbd li ol p pre s small sup sub strong strike table tbody th tr td ul br hr div span'.split()
  validAttrs = 'src width height alt title class href target'.split()
  urlAttrs = 'href title'.split() # Attributes which should have a URL
  
  soup = BeautifulSoup(value.decode('utf-8'))
  for comment in soup.findAll(text=lambda text: isinstance(text, Comment)):
    # Get rid of comments
    comment.extract()
  for tag in soup.findAll(True):
    if tag.name not in validTags:
      tag.hidden = True
    attrs = tag.attrs
    tag.attrs = []
    for attr, val in attrs:
      if attr in validAttrs:
        val = re_scripts.sub('', val) # Remove scripts (vbs & js)
        if attr in urlAttrs:
          val = urljoin(base_url, val) # Calculate the absolute url
        tag.attrs.append((attr, val))

  out = soup.renderContents().decode('utf8')
  cache.set(key, out, namespace="filters")
  return out  


  

SYMBOLS = {
  "->": "→", 
  "<-": "←", 
  "<->": "↔", 
  "(c)": "©", 
  "(r)": "®", 
  "(tm)": "™", 
  "<3": "♥",
  "x^2": "x²"     
}

  
EMOTICONS = {
 '#-o': '<img src="http://jupo.s3.amazonaws.com/emoticons/40.gif" alt="d\'oh">',
 '#:-S': '<img src="http://jupo.s3.amazonaws.com/emoticons/18.gif" alt="whew!">',
 '>-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/61.gif" alt="alien">',
 '>:)': '<img src="http://jupo.s3.amazonaws.com/emoticons/19.gif" alt="devil">',
 '>:D<': '<img src="http://jupo.s3.amazonaws.com/emoticons/6.gif" alt="big hug">',
 '>:P': '<img src="http://jupo.s3.amazonaws.com/emoticons/47.gif" alt="phbbbbt">',
 '<):)': '<img src="http://jupo.s3.amazonaws.com/emoticons/48.gif" alt="cowboy">',
 '<:-P': '<img src="http://jupo.s3.amazonaws.com/emoticons/36.gif" alt="party">',
 '<:o)': '<img src="http://jupo.s3.amazonaws.com/emoticons/36.gif" alt="party">',
 '(%)': '<img src="http://jupo.s3.amazonaws.com/emoticons/75.gif" alt="yin yang">',
 '(*)': '<img src="http://jupo.s3.amazonaws.com/emoticons/79.gif" alt="star">',
 '(:|': '<img src="http://jupo.s3.amazonaws.com/emoticons/37.gif" alt="yawn">',
 '**==': '<img src="http://jupo.s3.amazonaws.com/emoticons/55.gif" alt="flag">',
 '/:)': '<img src="http://jupo.s3.amazonaws.com/emoticons/23.gif" alt="raised eyebrows">',
 '8->': '<img src="http://jupo.s3.amazonaws.com/emoticons/105.gif" alt="day dreaming">',
 '8-X': '<img src="http://jupo.s3.amazonaws.com/emoticons/59.gif" alt="skull">',
# '8-|': '<img src="http://jupo.s3.amazonaws.com/emoticons/29.gif" alt="rolling eyes">',  # duplicate with nerd
 '8-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/29.gif" alt="rolling eyes">',
 '8-}': '<img src="http://jupo.s3.amazonaws.com/emoticons/35.gif" alt="silly">',
 ':!!': '<img src="http://jupo.s3.amazonaws.com/emoticons/110.gif" alt="hurry up!">',
 ':">': '<img src="http://jupo.s3.amazonaws.com/emoticons/9.gif" alt="blushing">',
 ':>': '<img src="http://jupo.s3.amazonaws.com/emoticons/15.gif" alt="smug">',
 ':(': '<img src="http://jupo.s3.amazonaws.com/emoticons/2.gif" alt="sad">',
 ':-(': '<img src="http://jupo.s3.amazonaws.com/emoticons/2.gif" alt="sad">',
 ':((': '<img src="http://jupo.s3.amazonaws.com/emoticons/20.gif" alt="crying">',
 ":'(": '<img src="http://jupo.s3.amazonaws.com/emoticons/20.gif" alt="crying">',
 ':(|)': '<img src="http://jupo.s3.amazonaws.com/emoticons/51.gif" alt="monkey">',
 ':)': '<img src="http://jupo.s3.amazonaws.com/emoticons/1.gif" alt="happy">',
 ':-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/1.gif" alt="happy">',
 ':)>-': '<img src="http://jupo.s3.amazonaws.com/emoticons/67.gif" alt="peace sign">',
 ':))': '<img src="http://jupo.s3.amazonaws.com/emoticons/21.gif" alt="laughing">',
 ':)]': '<img src="http://jupo.s3.amazonaws.com/emoticons/100.gif" alt="on the phone">',
 ':-"': '<img src="http://jupo.s3.amazonaws.com/emoticons/65.gif" alt="whistling">',
 ':-$': '<img src="http://jupo.s3.amazonaws.com/emoticons/32.gif" alt="don\'t tell anyone">',
 ':$': '<img src="http://jupo.s3.amazonaws.com/emoticons/32.gif" alt="don\'t tell anyone">',
 ':-#': '<img src="http://jupo.s3.amazonaws.com/emoticons/32.gif" alt="don\'t tell anyone">',
 ':-&': '<img src="http://jupo.s3.amazonaws.com/emoticons/31.gif" alt="sick">',
 ':-<': '<img src="http://jupo.s3.amazonaws.com/emoticons/46.gif" alt="sigh">',
 ':-*': '<img src="http://jupo.s3.amazonaws.com/emoticons/11.gif" alt="kiss">',
 ':-/': '<img src="http://jupo.s3.amazonaws.com/emoticons/7.gif" alt="confused">',
 ':-?': '<img src="http://jupo.s3.amazonaws.com/emoticons/39.gif" alt="thinking">',
 '*-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/39.gif" alt="thinking">',
 ':-??': '<img src="http://jupo.s3.amazonaws.com/emoticons/106.gif" alt="I don\'t know">',
 ':^)': '<img src="http://jupo.s3.amazonaws.com/emoticons/106.gif" alt="I don\'t know">',
 ':-B': '<img src="http://jupo.s3.amazonaws.com/emoticons/26.gif" alt="nerd">',
 '8-|': '<img src="http://jupo.s3.amazonaws.com/emoticons/26.gif" alt="nerd">',
 ':-O': '<img src="http://jupo.s3.amazonaws.com/emoticons/13.gif" alt="surprise">',
 ':o': '<img src="http://jupo.s3.amazonaws.com/emoticons/13.gif" alt="surprise">',
 ':-SS': '<img src="http://jupo.s3.amazonaws.com/emoticons/42.gif" alt="nail biting">',
 ':-ss': '<img src="http://jupo.s3.amazonaws.com/emoticons/42.gif" alt="nail biting">',
 ':-S': '<img src="http://jupo.s3.amazonaws.com/emoticons/17.gif" alt="worried">',
 ':-s': '<img src="http://jupo.s3.amazonaws.com/emoticons/17.gif" alt="worried">',
 ':s': '<img src="http://jupo.s3.amazonaws.com/emoticons/17.gif" alt="worried">',
 ':-bd': '<img src="http://jupo.s3.amazonaws.com/emoticons/113.gif" alt="thumbs up">',
 ':-c': '<img src="http://jupo.s3.amazonaws.com/emoticons/101.gif" alt="call me">',
 ':-h': '<img src="http://jupo.s3.amazonaws.com/emoticons/103.gif" alt="wave">',
 ':-q': '<img src="http://jupo.s3.amazonaws.com/emoticons/112.gif" alt="thumbs down">',
 ':-t': '<img src="http://jupo.s3.amazonaws.com/emoticons/104.gif" alt="time out">',
 ':-w': '<img src="http://jupo.s3.amazonaws.com/emoticons/45.gif" alt="waiting">',
 ':@)': '<img src="http://jupo.s3.amazonaws.com/emoticons/49.gif" alt="pig">',
 ':D': '<img src="http://jupo.s3.amazonaws.com/emoticons/4.gif" alt="big grin">',
 ':-D': '<img src="http://jupo.s3.amazonaws.com/emoticons/4.gif" alt="big grin">',
 ':d': '<img src="http://jupo.s3.amazonaws.com/emoticons/4.gif" alt="big grin">',
 ':O)': '<img src="http://jupo.s3.amazonaws.com/emoticons/34.gif" alt="clown">',
 ':P': '<img src="http://jupo.s3.amazonaws.com/emoticons/10.gif" alt="tongue">',
 ':p': '<img src="http://jupo.s3.amazonaws.com/emoticons/10.gif" alt="tongue">',
 ':-P': '<img src="http://jupo.s3.amazonaws.com/emoticons/10.gif" alt="tongue">',
 ':^o': '<img src="http://jupo.s3.amazonaws.com/emoticons/44.gif" alt="liar">',
 ':ar!': '<img src="http://jupo.s3.amazonaws.com/emoticons/pirate_2.gif" alt="pirate">',
 ':x': '<img src="http://jupo.s3.amazonaws.com/emoticons/8.gif" alt="love struck">',
# '<3': '<img src="http://jupo.s3.amazonaws.com/emoticons/8.gif" alt="love struck">',
 ':|': '<img src="http://jupo.s3.amazonaws.com/emoticons/22.gif" alt="straight face">',
 ':-|': '<img src="http://jupo.s3.amazonaws.com/emoticons/22.gif" alt="straight face">',
 ';)': '<img src="http://jupo.s3.amazonaws.com/emoticons/3.gif" alt="winking">',
 ';-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/3.gif" alt="winking">',
 ';))': '<img src="http://jupo.s3.amazonaws.com/emoticons/71.gif" alt="hee hee">',
 ';;)': '<img src="http://jupo.s3.amazonaws.com/emoticons/5.gif" alt="batting eyelashes">',
 '=((': '<img src="http://jupo.s3.amazonaws.com/emoticons/12.gif" alt="broken heart">',
 '=))': '<img src="http://jupo.s3.amazonaws.com/emoticons/24.gif" alt="rolling on the floor">',
 '=;': '<img src="http://jupo.s3.amazonaws.com/emoticons/27.gif" alt="talk to the hand">',
 '=D>': '<img src="http://jupo.s3.amazonaws.com/emoticons/41.gif" alt="applause">',
 '=P~': '<img src="http://jupo.s3.amazonaws.com/emoticons/38.gif" alt="drooling">',
 '@-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/43.gif" alt="hypnotized">',
 '@};-': '<img src="http://jupo.s3.amazonaws.com/emoticons/53.gif" alt="rose">',
 'B-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/16.gif" alt="cool">',
 'I-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/28.gif" alt="sleepy">',
 '|-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/28.gif" alt="sleepy">',
 'L-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/30.gif" alt="loser">',
 'O:-)': '<img src="http://jupo.s3.amazonaws.com/emoticons/25.gif" alt="angel">',
 'X(': '<img src="http://jupo.s3.amazonaws.com/emoticons/14.gif" alt="angry">',
 ':@': '<img src="http://jupo.s3.amazonaws.com/emoticons/14.gif" alt="angry">',
 ':-@': '<img src="http://jupo.s3.amazonaws.com/emoticons/14.gif" alt="angry">',
 'X_X': '<img src="http://jupo.s3.amazonaws.com/emoticons/109.gif" alt="I don\'t want to see">',
 '[-(': '<img src="http://jupo.s3.amazonaws.com/emoticons/33.gif" alt="no talking">',
 '[-O<': '<img src="http://jupo.s3.amazonaws.com/emoticons/63.gif" alt="praying">',
 '[..]': '<img src="http://jupo.s3.amazonaws.com/emoticons/transformer.gif" alt="transformer*">',
 '\\:D/': '<img src="http://jupo.s3.amazonaws.com/emoticons/69.gif" alt="dancing">',
 '\\m/': '<img src="http://jupo.s3.amazonaws.com/emoticons/111.gif" alt="rock on!">',
 '^#(^': '<img src="http://jupo.s3.amazonaws.com/emoticons/114.gif" alt="it wasn\'t me">',
 '^:)^': '<img src="http://jupo.s3.amazonaws.com/emoticons/77.gif" alt="not worthy">',
 'o=>': '<img src="http://jupo.s3.amazonaws.com/emoticons/73.gif" alt="billy">',
 '~O)': '<img src="http://jupo.s3.amazonaws.com/emoticons/57.gif" alt="coffee">',
 '~X(': '<img src="http://jupo.s3.amazonaws.com/emoticons/102.gif" alt="at wits\' end">',
 ':-L': '<img src="http://jupo.s3.amazonaws.com/emoticons/62.gif" alt="frustrated">',
 
 '(y)': '<img src="http://jupo.s3.amazonaws.com/emoticons/thumbs-up.png" alt="thumbs up">'
 
 }


if __name__ == "__main__":
#  text = '@[Tuan Long](user:3e8f2dfd-94c9-418e-a1b2-bddbb96cc8e0): File gốc đây - In hộ tớ nhá'
#  print flavored_markdown(text)
#  
  text = '''The Video took a lot of my tears...
  http://www.youtube.com/watch?v=W86jlvrG54o'''
  
  text = '''Done em nhe
  Details:
  https://docs.google.com/a/joomsolutions.com/spreadsheet/ccc?key=0AkUXu_Ee2OmydERLX3pzTkZacG45UW5PdEJtanRtUWc#gid=0
  '''
  print autolink(text)
  
  
  
  