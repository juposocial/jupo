#! coding: utf-8
# pylint: disable-msg=W0311, E1103, E1101
import re
import nose
import random
import requests
import main

# Test account 
USERNAME = 'aloneroad@gmail.com'
PASSWORD = '123456'
app = main.app.test_client()

_multiprocess_can_split_ = True

def send_options_request(*args, **kwargs):
  return app.open(*args, method='OPTIONS', **kwargs)

def send_get_request(*args, **kwargs):
  return app.open(*args, method='GET', as_tuple=True, **kwargs)

def send_head_request(*args, **kwargs):
  try:
    return app.open(*args, method='HEAD', 
                    as_tuple=True, follow_redirects=True, **kwargs)
  except RuntimeError:
    return app.open(*args, method='HEAD', 
                    as_tuple=True, **kwargs)
    
  
  
def sign_in(username=USERNAME, password=PASSWORD):
  login_page = send_options_request('/sign_in')
  assert '_csrf_token' in login_page.data

  csrf_token = re.compile('[a-z0-9]{40}').findall(login_page.data)[0]
  
  data = {'email': username,
          'password': password,
          '_csrf_token': csrf_token}
  return app.post('/sign_in', data=data, follow_redirects=True)

def sign_out():
  return app.get('/sign_out', follow_redirects=True)


def test_sign_in_sign_out():
  r = sign_in(USERNAME, '123')
  assert 'Welcome back,' not in r.data
  assert 'Sign out' not in r.data
  assert 'Sign in' in r.data
  
  r = sign_in('foo', 'bar')
  assert 'Welcome back,' not in r.data
  assert 'Sign out' not in r.data
  assert 'Sign in' in r.data
  
  r = sign_in(USERNAME.upper(), PASSWORD)
  assert 'Welcome back,' in r.data
  assert 'Sign out' in r.data
  
  r = sign_out()
  assert 'Sign out' not in r.data
  assert 'New to 5works' in r.data


def test_home():
  r = app.get('/', follow_redirects=True)
  assert 'New to 5works' in r.data
  assert 'Discover' in r.data
  assert 'Sign in' in r.data
  
  assert 'Welcome back,' not in r.data
  assert 'Comment' not in r.data
  assert '☆' not in r.data
  assert 'options' not in r.data
  
  
def test_seasurf_protection():
  data = {'email': USERNAME,
          'password': PASSWORD}
  r = app.post('/sign_in', data=data)
  assert 'Forbidden' in r.data
  assert 'Go home' in r.data
  
  assert 'Welcome back,' not in r.data
  assert 'Sign out' not in r.data
  
  
@nose.with_setup(sign_in, sign_out)
def test_discover():  
  r = app.get('/discover')
  r2 = send_options_request('/discover')
  
  assert ['Discover' in html \
          for html in (r.data, r2.data)].count(True) == 2
  assert ['Share something with the world' in html \
          for html in (r.data, r2.data)].count(True) == 2
  assert ['options' in html \
          for html in (r.data, r2.data)].count(True) == 2
  assert ['Comment' in html \
          for html in (r.data, r2.data)].count(True) == 2
  assert ['forward-icon' in html \
          for html in (r.data, r2.data)].count(True) == 2
  assert ['public-icon' in html \
          for html in (r.data, r2.data)].count(True) == 2
  assert ['star-icon' in html or 'starred-icon' in html \
          for html in (r.data, r2.data)].count(True) == 2
  assert ['friends-icon' in html \
          for html in (r.data, r2.data)].count(False) == 2
  assert ['lock-icon' in html \
          for html in (r.data, r2.data)].count(False) == 2  
    

@nose.with_setup(sign_in, sign_out)
def test_what_hot():  
  r = app.get('/hot')
  r2 = send_options_request('/hot')
  
  for html in [r.data, r2.data]:
    assert 'Share something with the world' in html
    assert 'options' in html
    assert 'Comment' in html
    assert 'forward-icon' in html
    assert 'star-icon' in html or 'starred-icon' in html
    assert 'public-icon' in html
    assert 'friends-icon' not in html
    assert 'lock-icon' not in html  


@nose.with_setup(sign_in, sign_out)
def test_starred_posts():  
  r = app.get('/starred')
  r2 = send_options_request('/starred')
  
  for html in [r.data, r2.data]:
    assert 'options' in html
    assert 'Comment' in html
    assert 'forward-icon' in html
    assert 'starred-icon' in html
    assert 'public-icon' in html
    assert 'friends-icon' not in html
    assert 'lock-icon' not in html  
  
    # TODO: make sure all posts is starred
#      print re.compile('data-href.*?/unstar').findall(html)
#      assert re.compile('data-href.*?/unstar.*?data').findall(html) == []
  

@nose.with_setup(sign_in, sign_out)
def test_shared_by_me():  
  r = app.get('/shared_by_me')
  r2 = app.get('/shared_by_me')
  
  try:
    user_id = re.compile("<a.*?href=.*?user/(\d+).*?class=.*?username.*?</a>").findall(r.data)[0]
  except IndexError:
    assert False
  
  for html in [r.data, r2.data]:
    assert 'options' in html
    assert 'Comment' in html
    assert 'forward-icon' in html
    assert 'star-icon' in html or 'starred-icon' in html
    assert 'public-icon' in html
    assert 'friends-icon' not in html
    assert 'lock-icon' not in html  
    
    posts = len(re.compile('<section').findall(html))
    posts_with_username = len(re.compile('section.*?header.*?user/%s.*?class' % user_id).findall(html.replace('\n', '')))
    posts_of_mine = len(re.compile('section.*?header.*?your.*?</header>').findall(html.replace('\n', '')))
    assert posts == posts_with_username or posts == (posts_with_username + posts_of_mine)
  

@nose.with_setup(sign_in, sign_out)
def test_news_feed():
  r = app.get('/')
  r2 = send_options_request('/news_feed')
  
  for html in [r.data, r2.data]:
    assert 'options' in html
    assert 'Comment' in html
    assert 'Archive' in html
    assert 'Pin to Top' in html
    assert 'Last Activities' in html
    assert 'Write something...' in html
    assert 'forward-icon' not in html
    
  r3 = send_options_request('/news_feed/page2')
  r4 = send_options_request('/news_feed/page3')
  
  for html in [r3.data, r4.data]:
    assert 'options' in html
    assert 'Comment' in html
    assert 'Archive' in html
    assert 'Pin to Top' in html
    assert 'forward-icon' not in html
    
  sign_out()
  
  r = app.get('/news_feed', follow_redirects=True) # redirect to discover
  assert "What are you working on" not in r.data
  assert "Archive" not in r.data
  assert "Pin to Top" not in r.data
    
  assert 'New to 5works' in r.data
  assert 'Sign in' in r.data
    
@nose.with_setup(sign_in, sign_out)
def test_feed():
  html = app.get('/news_feed').data
  urls = re.compile('(/feed/\d+)(?:[\'|"])').findall(html)
  urls = random.sample(set(urls), 3)
  print urls
  for url in urls:
    r = send_options_request(url)
    if 'public-icon' in r.data:
      assert 'star' in r.data
      assert 'forward' in r.data
    else:
      assert 'Read Receipts' in r.data

    assert 'Comment' in r.data
    assert 'new-comment' in r.data
    
    

@nose.with_setup(sign_in, sign_out)
def test_notes():
  r = app.get('/docs')
  r2 = send_options_request('/docs')
  
  for html in [r.data, r2.data]:
    assert 'options' in html
    assert 'Comment' in html
    assert 'Edit' in html
    assert 'forward-icon' not in html
    assert re.compile('<header.*?/user/*.?>').findall(html) == [] 
  

@nose.with_setup(sign_in, sign_out)
def test_note():
  html = app.get('/docs').data
  urls = re.compile('(/doc/\d+)(?:[\'|"])').findall(html)
  urls = random.sample(set(urls), 3)
  print urls
  for url in urls:
    r = send_options_request(url, as_tuple=True)
    assert 'Comment' in r[1].data
    assert 'new-comment' in r[1].data
    if 'Official' not in r[1].data:
      assert 'Edit' in r[1].data
      assert 'additions' in r[1].data
      assert 'deletions' in r[1].data
      assert 'Revision History' in r[1].data
      assert 'Recent Docs' in r[1].data
    assert r[1].status_code == 200


@nose.with_setup(sign_in, sign_out)
def test_files():
  r = app.get('/files')
  r2 = send_options_request('/files')
  
  for html in [r.data, r2.data]:
    assert 'Browse...' in html
    assert 'Recent Attachments' in html
    assert 'options' in html
    assert 'Comment' in html
    assert 'New Version' in html
    assert 'Rename' in html
    
    
@nose.with_setup(sign_in, sign_out)
def test_file():
  html = app.get('/files').data
  urls = re.compile('(/file/\d+)(?:[\'|"])').findall(html)
  urls = random.sample(set(urls), 3)
  print urls
  for url in urls:
    r = send_options_request(url)
    assert 'Comment' in r.data
    assert 'Rename' in r.data
    assert 'New Version' in r.data
    assert 'new-comment' in r.data
    assert 'History' in r.data


@nose.with_setup(sign_in, sign_out)
def test_notifications():  
  r = app.get('/notifications')
  assert 'Notifications' not in r.data
  assert 'illegal request' in r.data
  
  r2 = send_options_request('/notifications')
  assert 'Notifications' in r2.data


@nose.with_setup(sign_in, sign_out)
def test_groups():
  html = send_options_request('/groups').data
  urls = re.compile('(/group/\d+)').findall(html)
  print urls
  for url in set(urls):
    r = app.get(url)
    r2 = send_options_request(url)
    for content in [r.data, r2.data]:
#      assert 'Leave a message...' in content
      assert 'Member' in content or 'Follower' in content
      assert 'Unresolved Tasks' in content
      assert 'Docs' in content
      assert 'Files' in content
      assert 'Recently Viewed' in content
      if 'section' in content:
        assert 'View Single Post' in content
        assert 'Comment' in content
        

@nose.with_setup(sign_in, sign_out)
def test_search():
  html = send_options_request('/search?query=aaaaaaaaaaaaaaaaaaaaaa').data
  assert '0 results' in html
  assert 'In conversation with' in html
  
  html = send_options_request('/search?query=a').data
  assert ' 0 results' not in html # note: space before 0
  assert 'In conversation with' in html
  
  sign_out()
  
  html = send_options_request('/search?query=a').data
  assert '0 results' not in html
  assert 'In conversation with' not in html
  
  

@nose.with_setup(sign_in, sign_out)
def test_spelling_suggestion():
  html = send_options_request('/search?query=hello+word').data
  assert 'hello world' in html
  

def test_users():
  html = send_options_request('/news_feed').data
  urls = re.compile('/user/\d+').findall(html)
  for url in set(urls):
    r = app.get(url)
    r2 = send_options_request(url)
    for content in [r.data, r2.data]:
      assert 'Leave his a message...' in content or 'Leave her a message...' in content
      assert 'Member of' in content
      assert 'Following' in content
      assert 'Starred' in content
      if 'section' in content:
        assert 'Comment' in content
        assert 'Archive' not in content


@nose.with_setup(sign_in, sign_out)
def test_settings():
  html = app.get('/').data
  urls = re.findall('/user/\d+/settings', html)
  html = send_options_request(urls[0]).data
  assert 'Male' in html
  assert 'Female' in html
  assert 'Change password' in html
  assert 'Save Changes' in html
  assert 'preview' in html
  assert 'pickfile' in html
  assert 'attachments' in html


@nose.with_setup(sign_in, sign_out)
def test_avatar():
  r = app.get('/')
  avatar_url = re.compile("img src='(.*?_60.jpg)'").findall(r.data)[0]
  
  r = requests.head(avatar_url)
  assert r.status_code == 200
  assert r.headers['Content-Type'] == 'image/jpeg'
  assert r.headers['Expires'] == '31 December 2037 23:59:59 GMT'
  assert r.headers['Cache-Control'] == 'public, max-age=315360000'
  
  r = requests.head(avatar_url.replace('_60.jpg', '.jpg'))
  assert r.status_code == 403
  
  
@nose.with_setup(sign_in, sign_out)
def test_attachment():
  html = app.get('/files').data
  
  posts = html.split('</section>')
  for post in posts:
    if 'Public' not in post:
      private_attachments = re.findall('/attachment/\d+\?rel=\d+', post)
      break
  
  attachment_url = private_attachments[0]
  attachment_url_without_rel = attachment_url.split('?', 1)[0]
  attachment_url_with_fake_rel = attachment_url_without_rel + '?rel=123'
  
  status_code = send_head_request(attachment_url_without_rel)[1].status_code
  assert status_code in [200, 301]
  
  status_code = send_head_request(attachment_url_with_fake_rel)[1].status_code
  assert status_code == 404

  status_code = send_head_request(attachment_url)[1].status_code
  assert status_code in [200, 301]
  
  sign_out()
  
  status_code = send_head_request(attachment_url_without_rel)[1].status_code
  assert status_code == 403
  
  status_code = send_head_request(attachment_url)[1].status_code
  assert status_code == 404
  
  for post in posts:
    if 'Public' in post:
      public_attachments = re.findall('/attachment/\d+\?rel=\d+', post)
      break
  
  attachment_url = public_attachments[0]
  attachment_url_without_rel = attachment_url.split('?', 1)[0]
  attachment_url_with_fake_rel = attachment_url_without_rel + '?rel=123'
  
  status_code = send_head_request(attachment_url_without_rel)[1].status_code
  assert status_code == 403
  
  status_code = send_head_request(attachment_url)[1].status_code
  assert status_code == 200
  

#@nose.with_setup(sign_in, sign_out)
#def test_all_urls():
#  html = app.get('/hot').data
#  
#  urls = re.compile('href="(.*?)".*?>').findall(html)
#  urls.extend(re.compile("href='(.*?)'.*?>").findall(html))
#  urls = set(urls)
#  
#  print urls
#  for url in urls:
#    if url.startswith('http') or url.startswith('//'):
#      continue
#    elif url == '/sign_out' or 'public/' in url or 'favicon.ico' in url or 'shortcuts' in url:
#      continue
#    elif '/remove' in url or '/unstar' in url or '/star' in url:
#      continue
#    elif url.startswith('#!'):
#      url = url[2:]
#      r = app.open(url, method='OPTIONS', as_tuple=True)
#      assert r[0] == 200
#    elif url.startswith('/'):
#      r = app.get(url, as_tuple=True)
#      assert r[0] == 200
#    else:
#      continue

#def test_footer_links():
#  pass

#def test_public_files():
#  r = app.get('public/images/tasks.png')
#  assert r.headers['Content-Length'] == '4472'
#  assert r.headers['Content-Type'] == 'image/png'
#
#  r = app.get('public/scripts/main.js')
#  print r.data
#  assert r.headers['Content-Type'] == 'application/javascript'
#  pass

def test_post():
  pass

def test_comment():
  pass

def test_public_discover_next_pages():
  for i in range(2, 3):
    html = send_options_request('/discover/page%s' % i).data
    if html:
      assert 'section' in html
      assert 'Share something with the world' not in html
      assert 'options' not in html
      assert 'Comment' not in html
      assert 'friends-icon' not in html
      assert 'lock-icon' not in html
      
def test_public_discover():
  html = app.get('/discover').data
  assert 'View Single Post' in html
  assert 'Feature Groups' in html
  
  urls = re.findall('/feed/\d+', html)
  for url in urls[:5]:
    r1 = send_options_request(url)    
    r2 = app.get(url)
    for data in [r1.data, r2.data]:
      assert 'new-comment' not in data
      assert 'Comment' not in data
      assert 'Archive' not in data
      assert 'Pin to Top' not in data
      
  urls = re.findall('/group/\d+', html)
  for url in urls:
    if '340915856517103617' in url: # Feedback group (only exists on production)
      continue
    r1 = send_options_request(url)    
    r2 = app.get(url)
    for data in [r1.data, r2.data]:
      assert 'new-comment' not in data
      if 'lock-icon' in data: # closed group
        assert 'friends-icon' not in data
        assert 'section' not in data
        assert 'Comment' not in data
        assert 'Members' in data

def test_js_files():
  code = app.get('/public/scripts/lib.js').data
  assert 'this.' in code
  assert '$.' in code
  
  code = app.get('/public/scripts/main.js').data
  assert '.ready' in code
  assert 'function refresh(' in code

def test_css_files():
  code = app.get('/public/styles/home.css').data
  assert '#menu-toggle' in code
  assert '#left-sidebar' in code
  assert '#overlay' in code
  

if __name__ == '__main__':
  argv = ['--nocapture']
  nose.main(argv=argv)
  
  