
import pymongo

def setup_test_database():
  db = pymongo.Connection();
  db.drop_database('_play_jupo_dev')
  db.copy_database('play_jupo_dev', '_play_jupo_dev')
  db.drop_database('play_jupo_dev')
  
def teardown_test_database():
  db = pymongo.Connection()
  db.drop_database('play_jupo_dev')
  db.copy_database('_play_jupo_dev', 'play_jupo_dev')
  db.drop_database('_play_jupo_dev')