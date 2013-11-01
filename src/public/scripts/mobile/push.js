
$.global = {};

function incr(id, value) {
  var item = $(id);
  var value = typeof (value) != 'undefined' ? value : 1;
  if (item.html() == '...') {
    return false;
  }
  value = parseInt(item.html()) + parseInt(value);
  item.html(value);
  if (value != 0) {
    item.show();
  }
  
  return value;
}

function decr(id, value) {
  var item = $(id);
  var value = typeof (value) != 'undefined' ? value : 1;
  value = parseInt(item.html()) - parseInt(value);
  
  if (value < 0) {
    value = 0;
  }
  item.html(value);
  
  if (value == 0) {
    item.hide();
  }
  
  return value;
}


var source = new EventSource('/stream');

source.onopen = function(e) {
  console.log('Stream: listening...');
};

source.onerror = function(e) {
  switch (e.target.readyState) {
     case EventSource.CONNECTING:  
        console.log('Reconnecting...');  
        break;
     case EventSource.CLOSED:  
        break;    
     default: 
        break;    
     
  }  
};

source.onmessage = function(e) {
  console.log(e);
  var event = window.JSON.parse(e.data);

  if (event.type == 'friends-online') {
    user = event.user;
    // Update user status led
    $('.user-' + user.id + '-status').removeClass('online offline away').addClass(user.status);

  } else if (event.type == 'unread-feeds' && window.location.pathname.indexOf('/group/') == -1) {
    
    var feed_id = $(event.info).attr('id');
    console.log('new: ' + feed_id);
    

    if ($('#' + feed_id).length != 0) { // feed existed. append comment only

      var comment = $('div.comments-list li.comment:last-child', $(event.info));

      if (comment.length != 0 && $('#' + comment.attr('id')).length == 0) {
        
        $('#' + feed_id + ' ul.comments').removeClass('hidden');
        $('#' + feed_id + ' div.comments-list').append(comment);
        $('#' + feed_id).addClass('unread');
        $('#' + feed_id + ' li.comment:last-child').addClass('unread');

        // update comment counter
        incr('#' + feed_id + ' .quick-stats .comment-count', 1);
        incr('#' + feed_id + ' .comments-list .comment-count', 1);

        // set read-receipts to "No one"
        $('#' + feed_id + ' a.quick-stats .receipt-icon').remove();
        $('#' + feed_id + ' a.quick-stats .read-receipts-count').remove();
        $('#' + feed_id + ' li.read-receipts').html('<i class="receipt-icon"></i> Seen by no one.');

        refresh();  // refresh timeago
        
        msg = $('.message .text', comment).text().replace(/\s\s+/, ' ').slice(0, 50);
        username = $('.message strong', comment).html();
        avatar = $('img.small-avatar', comment).attr('src');

      }

    } else {
      if (window.location.pathname.indexOf('/news_feed') != -1) {
        $('ul.stream').prepend(event.info);

        $('div#unread-messages').show();
        refresh();
        
      }
    }
    
        
  } else if (event.type && event.type.indexOf('unread-feeds') != -1) {

    if (event.type.indexOf('|') != -1) {
      
      
      var group_id = event.type.split('|')[0];
      var feed = $(event.info);
      
     
      if (window.location.pathname.indexOf(group_id) != -1) {
        var feed_id = feed.attr('id');
        
        console.log('(group) new post: ' + feed_id);
          
        if ($('#' + feed_id).length) {// feed existed. append comment only

          var comment = $('div.comments-list li:last-child', $(event.info));

          if (comment.length != 0 && $('#' + comment.attr('id')).length == 0) {

            $('#' + feed_id + ' ul.comments').removeClass('hidden');
            $('#' + feed_id + ' div.comments-list').append(comment);
            $('#' + feed_id).addClass('unread');
            $('#' + feed_id + ' li.comment:last-child').addClass('unread');

            // update comment counter
            incr('#' + feed_id + ' .quick-stats .comment-count', 1);
            incr('#' + feed_id + ' .comments-list .comment-count', 1);

            // remove read-receipts
            $('#' + feed_id + ' a.quick-stats .receipt-icon').remove();
            $('#' + feed_id + ' a.quick-stats .read-receipts-count').remove();
            $('#' + feed_id + ' li.read-receipts').html('<i class="receipt-icon"></i> Seen by no one.');

            refresh();
          }
          

        } else {
          $('ul.stream').prepend(event.info);

          $('span#unread').html($('ul.stream > li.hidden').length);
          $('div#unread-messages').show();
            
          refresh();
          
        }
      }
    }

  } else if (event.type == 'read-receipts') {
    
    var text = event.info.text;
    var post_id = event.info.post_id;
    var quick_stats = event.info.quick_stats;
    var viewers = event.info.viewers;
 
 
    $.global._tmp = event;

    $('#post-' + post_id + ' a.quick-stats span.read-receipts').html(quick_stats);
    
    if (quick_stats.indexOf('>0<') == -1) {
      $('#post-' + post_id + ' a.quick-stats span.read-receipts').removeClass('hidden');
    } else {
      $('#post-' + post_id + ' a.quick-stats span.read-receipts').addClass('hidden'); 
    }

    $('#post-' + post_id + ' a.quick-stats').attr('title', text);
    
    $('#post-' + post_id + ' a.remove-comment').remove();

    $('#post-' + post_id + ' ul.menu a.remove').parent().remove();

  } else if (event.type == 'likes' ) {
    var html_code = event.info.html;
    var post_id = event.info.post_id;
    var quick_stats = event.info.quick_stats;

    $('#post-' + post_id + ' a.quick-stats span.likes').html(quick_stats);
    if (quick_stats.indexOf('>0<') == -1) {
      $('#post-' + post_id + ' a.quick-stats span.likes').removeClass('hidden');
    } else {
      $('#post-' + post_id + ' a.quick-stats span.likes').addClass('hidden'); 
    }
        
    $('#post-' + post_id + ' li.likes').remove();

    $('#post-' + post_id + ' div.comments-list').prepend(html_code);

  } else if (event.type == 'like-comment') {
    
    $('#comment-' + event.info.comment_id + ' .likes .counter').html(event.info.likes_count);
    
    if (event.info.likes_count == 0) {
      $('#comment-' + event.info.comment_id + ' .likes').addClass('hidden');
    } else {
      $('#comment-' + event.info.comment_id + ' .likes').removeClass('hidden');
    }
    
    $('#comment-' + event.info.comment_id + ' .likes').attr('original-title', event.info.text);
    
  }
  
  else if (event.type == 'remove') {
    
    if (event.info.comment_id) {
      $('#comment-' + event.info.comment_id).remove();
    }
    
    else if (event.info.post_id) {
      if ($('#post-' + event.info.post_id + ' div.undo').length == 0) {
        $('#post-' + event.info.post_id).remove();
      }
    }
    
  } else if (event.type == 'update') {
    if (event.info.comment_id) {
      $('#comment-' + event.info.comment_id + ' div.message .text:not(.hidden)').html(event.info.text);
      $('#comment-' + event.info.comment_id + ' div.message .text.hidden').html(event.info.changes);
      $('#comment-' + event.info.comment_id + ' a.see-changes').attr('original-title', 'Click to see changes');
    }
  }
  
};