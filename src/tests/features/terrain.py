#! coding: utf-8
# pylint: disable-msg=W0311, W0611, E1103, E1101
#@PydevCodeAnalysisIgnore

from lettuce import before, after, world
from selenium import webdriver
from fixtures import db

@before.all
def setup_browser():
  world.browser = webdriver.Firefox()
    
@after.all
def close_browser(total):
  world.browser.close()
  

@before.each_feature
def setup_db(feature):
  db.setup_test_database()
   
@after.each_feature
def teardown_db(feature):
  db.teardown_test_database()