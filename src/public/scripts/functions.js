  

function toggle_chatbox(chatbox_id) {
  
  var chatbox = $('#' + chatbox_id);
  
  if (chatbox.hasClass('minimize')) {
    localStorage.removeItem('state-' + chatbox_id)
  } else {
    localStorage['state-' + chatbox_id] = 'minimize'
  }
  
  chatbox.toggleClass('minimize');
  
  return true;
}

function close_chat(chat_id) {
  
  localStorage.removeItem('state-chat-' + chat_id);
  $('#chat-' + chat_id).parents('.inflow').remove();
  
  var chat_ids = localStorage.getItem('chats').split(',');
  chat_ids.pop(chat_id);
  
  out = [];
  for (var i = 0; i < chat_ids.length; i++) {
    var chat_id = chat_ids[i];
    
    if (chat_id != '' && chat_id.split('-')[1] != undefined && isNaN(chat_id.split('-')[1]) == false) {
      out.push(chat_id);
    }
  }
 
  localStorage['chats'] = out.join(',')
  
  
  
  return true;
  
}
    
function start_chat(chat_id) {
  if (chat_id.indexOf('-') == -1) {
    return false;
  }
  
  if ($('#chat-' + chat_id).length > 0) {
      return false;
  }
  
  var parts = chat_id.split('-');
  if (parts.length != 2) {
    return false;
  }
  
  var href = '/chat/' + chat_id.replace('-', '/');

  show_loading();
  $.ajax({
    url: href,
    type: 'GET',
    success: function(html){ 
      hide_loading();
      
      if ($('#chat-' + chat_id).length > 0) {
          return false;
      }
      
      var chat_ids = localStorage.getItem('chats');
      if (chat_ids != undefined && chat_ids.indexOf(chat_id) == -1) {
        localStorage['chats'] = chat_ids + ',' + chat_id;
      } else {
        localStorage['chats'] = chat_id;
      }
      
      $('#chat').prepend(html);
      
      if (localStorage.getItem('state-chat-' + chat_id) == 'minimize') {
        toggle_chatbox('chat-' + chat_id);
      }
      
        
      $('#chat-' + chat_id + ' textarea.mentions').mentionsInput({
        minChars: 1,
        fullNameTrigger: false,
        onDataRequest: function(mode, query, callback) {
          search_mentions(query, callback)
        }
      });
      
      var textbox = $('#chat-' + chat_id + ' form textarea.mentions');
      var last_textbox_height = textbox.height();
      
      textbox.elastic();
      
      textbox.resize(function() { // resize messages panel 
        console.log('resized')
        
        var delta = ($('#chat-' + chat_id + ' form textarea.mentions').height() - last_textbox_height);
        var new_height = $('#chat-' + chat_id + ' .messages').height() - delta;
        
        $('#chat-' + chat_id + ' .messages').css('height', new_height + 'px');
        $('#chat-' + chat_id + ' .status').css('bottom', parseInt($('#chat-' + chat_id + ' .status').css('bottom')) + delta + 'px');
        
        last_textbox_height = $('#chat-' + chat_id + ' form textarea.mentions').height();
        
        
        $('#chat-' + chat_id + ' .messages').animate({
            scrollTop: 99999
        }, 'fast');
      
      })
    
      $('#chat-' + chat_id + ' .messages').animate({
          scrollTop: 99999
      }, 'fast');
      
      setTimeout(function() {
        $('#chat-' + chat_id + ' textarea.mentions').focus();
      }, 50)
    },
    error: function(data) {
      hide_loading();
    }
  });
  
  
}

function search_mentions(query, callback) {
      query = khong_dau(query).toLowerCase();
      data = _.filter($.global.coworkers, function(item) {
        return khong_dau(item.name).toLowerCase().indexOf(query) == 0;
        // prefix matching
      });
      
      var ids;
      var owners;
      ids = [];
      owners = [];
      for (i in data) {
        var id;
        id = data[i].id + data[i].name;
        if (ids.indexOf(id) == -1) {
          ids.push(id);
          owners.push(data[i]);
          
          if (owners.length == 3) {
            break
          }
        }
      }

      if (owners.length < 3) {
        for (i in $.global.coworkers) {
          var id;
          var item;
          item = $.global.coworkers[i];
          id = item.id + item.name;
          if (ids.indexOf(id) == -1 && khong_dau(item.name).toLowerCase().indexOf(query) > -1) {
            ids.push(id);
            owners.push(item);
          }

          if (owners.length == 3) {
            break
          }
        }

      }
      callback.call(this, owners);
}


function show_notification(img, title, description, timeout, callback) {
  var havePermission = window.webkitNotifications.checkPermission();
  if (havePermission == 0) {
    // 0 is PERMISSION_ALLOWED
    var notification = window.webkitNotifications.createNotification(img, title, description);

    notification.onclick = function () {
                notification.cancel();
                callback();
    }
    notification.show();
    
    setTimeout(function() {
              notification.close()
    }, timeout)
  } else {
      window.webkitNotifications.requestPermission();
  }
}

function update_title(title) {
    var pattern = /^\(.*?\) /gi;
    var count = document.title.match(pattern);
    if (count == null) {
      document.title = title;
    } else {
      document.title = count + title;
    }
}

function get_cookie(name) {
  var nameEQ = name + "=";
  var ca = document.cookie.split(';');
  for(var i=0;i < ca.length;i++) {
      var c = ca[i];
      while (c.charAt(0)==' ') c = c.substring(1,c.length);
      if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
  }
  return null;
}


function set_cookie(name, value, expires, path, domain, secure) {
  document.cookie = name + "=" + escape(value) + ((expires) ? "; expires=" + expires.toGMTString() : "") + ((path) ? "; path=" + path : "") + ((domain) ? "; domain=" + domain : "") + ((secure) ? "; secure" : "");
}

function delete_cookie(name, path, domain) {
  if(get_cookie(name)) {
    document.cookie = name + "=" + ((path) ? "; path=" + path : "") + ((domain) ? "; domain=" + domain : "") + "; expires=Thu, 01-Jan-70 00:00:01 GMT";
  }
}

function is_valid_email(email) { 
  var re = /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
  return re.test(email);
} 
      

function khong_dau(text) {
  return text.replace(/à|á|ạ|ả|ã|â|ầ|ấ|ậ|ẩ|ẫ|ă|ằ|ắ|ặ|ẳ|ẵ/g, "a").replace(/đ/g, "d").replace(/đ/g, "d").replace(/ỳ|ý|ỵ|ỷ|ỹ/g, "y").replace(/ù|ú|ụ|ủ|ũ|ư|ừ|ứ|ự|ử|ữ/g, "u").replace(/ò|ó|ọ|ỏ|õ|ô|ồ|ố|ộ|ổ|ỗ|ơ|ờ|ớ|ợ|ở|ỡ.+/g, "o").replace(/è|é|ẹ|ẻ|ẽ|ê|ề|ế|ệ|ể|ễ.+/g, "e").replace(/ì|í|ị|ỉ|ĩ/g, "i");
}

function preload_autocomplete() {
  if ($.global.autocomplete == null) {
    $.ajax({
      url: '/autocomplete',
      dataType: 'json',
      success: function(resp) {
        $.global.autocomplete = resp;

        if ($('form input.autocomplete').length > 0) {
            $('form input.autocomplete').tokenInput("setLocalData", resp);
        }

        $.global.coworkers = resp.filter(function(e) {
          return e.type == 'user'
        });
      }
    })
  }
  
  else {
    if ($('form input.autocomplete').length > 0) {
        $('form input.autocomplete').tokenInput("setLocalData", $.global.autocomplete);
    }
  }
}


function show_searchbox_dropdown(query) {   
  
  $('#main').attr('class', 'animate blur');
    
  if (!$.global.autocomplete) {
    preload_autocomplete();
  }

  if (query != '') {
      ids = [];
      html = '<div class="arrow-top-border"></div><div class="arrow-top"></div>';
      html += '<li><a class="async selected" title="Search for ' + query + '" href="/search?query=' + query + '"><i class="search-icon"></i> <strong>' + query + '</strong></a></li>';
      for (i in $.global.autocomplete) {
          var id;
          var item;
          item = $.global.autocomplete[i];
          id = item.id;
          _query = khong_dau(query).toLowerCase();
          if (id != 'public' && ids.indexOf(id) == -1 && khong_dau(item.name).toLowerCase().indexOf(_query) > -1) {
            ids.push(id);
            if (item.type == 'group') {
              html += '<li><a class="async" href="/group/' + item.id + '"><img class="micro-avatar" src="' + item.avatar + '"> ' + item.name + '</a></li>';
            } else {
              html += '<li><a class="async" href="/user/' + item.id + '"><img class="micro-avatar" src="' + item.avatar + '"> ' + item.name + '</a></li>';
            }
            
            if (ids.length >= 3) {
              break;
            }
            
          }
      }
      html += '<li><a class="popup" href="/search?type=people&query=' + query + '">&nbsp;Search all people for <strong>' + query + '</strong></a></li>';
      
      $('form#search-box ul.dropdown-menu').html(html).show();
  }
}

function hide_searchbox_dropdown() {
  unfocus_searchbox();
  
  if ($('#main').hasClass('blur')) {
    $('#main').attr('class', 'animate unblur');
  }
  $('form#search-box ul.dropdown-menu').hide();
}

function unfocus_searchbox() {
  // Unfocus search box
      $('form#search-box input').removeClass('highlight');
      $("form#search-box i.search-icon").removeClass("highlight");
      $('form#search-box .reset').hide();
      $('form#search-box .spinner').hide();
}


/* Enable/disable scrolling temporarily */
// left: 37, up: 38, right: 39, down: 40,
// spacebar: 32, pageup: 33, pagedown: 34, end: 35, home: 36
var keys = [37, 38, 39, 40];

function preventDefault(e) {
  e = e || window.event;
  if (e.preventDefault)
    e.preventDefault();
  e.returnValue = false;
}

function keydown(e) {
  for (var i = keys.length; i--; ) {
    if (e.keyCode === keys[i]) {
      preventDefault(e);
      return;
    }
  }
}

function wheel(e) {
  preventDefault(e);
}

function disable_scroll() {
  if (window.addEventListener) {
    window.addEventListener('DOMMouseScroll', wheel, false);
  }
  window.onmousewheel = document.onmousewheel = wheel;
  document.onkeydown = keydown;
}

function enable_scroll() {
  if (window.removeEventListener) {
    window.removeEventListener('DOMMouseScroll', wheel, false);
  }
  window.onmousewheel = document.onmousewheel = document.onkeydown = null;
}

/* Tour */
function start_tour() {

  // Start tour
  guiders.createGuider({
    buttons: [{
      name: "Take a Tour",
      onclick: function() {
        guiders.hideAll();
        $('li#news-feed > a.async').trigger('click');
        setTimeout(function() {
          guiders.next();
        }, 1000)
      }
    }],
    title: "Welcome to Jupo!",
    description: "Jupo is an online working environment. It keeps your discussions, notes, files, tasks and team together.",
    id: "tour-1",
    next: "tour-3",
    overlay: true,
  }).show();


  // guiders.createGuider({
    // attachTo: "#welcome-box",
    // autoFocus: true,
    // buttons: [{
      // name: "Exit Tour",
      // onclick: guiders.hideAll
    // }, {
      // name: "Next",
      // onclick: guiders.next
    // }],
    // title: "Customize your profile",
    // description: "Update your profile picture and share some interesting details about yourself",
    // onShow: disable_scroll,
    // onHide: enable_scroll,
    // id: "tour-2",
    // next: "tour-3",
    // position: 3,
    // offset: {
      // left: -35,
      // top: 27
    // }
  // });

  guiders.createGuider({
    attachTo: "tr#message",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Start Writing",
      onclick: guiders.next
    }],
    title: "Share the latest",
    description: "Compose a new message and send it to your coworkers",
    onShow: function() {
      disable_scroll();
      $('form#new-feed textarea.mention').focus();
    },
    onHide: enable_scroll,
    id: "tour-3",
    next: "tour-5",
    position: 7,
    offset: {
      left: -5,
      top: -30
    }
  });

  // guiders.createGuider({
    // attachTo: "a#focus",
    // autoFocus: true,
    // buttons: [{
      // name: "Exit Tour",
      // onclick: guiders.hideAll
    // }, {
      // name: "Next"
    // }],
    // title: "Assign this as a task",
    // description: "Set as a task with urgent, important or normal priority",
    // onShow: function() {
      // disable_scroll();
      // $('a#focus').trigger('click');
    // },
    // onHide: enable_scroll,
    // id: "tour-4",
    // next: "tour-5",
    // position: 7,
    // offset: {
      // left: -12,
      // top: -36
    // },
  // });

  guiders.createGuider({
    attachTo: "a#attach",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Next"
    }],
    title: "Attach files",
    description: "Add any files - easy as fast.",
    onShow: function() {
      disable_scroll();
      $('a#attach').trigger('click');
    },
    onHide: enable_scroll,
    id: "tour-5",
    next: "tour-6",
    position: 7,
    offset: {
      left: -12,
      top: -36
    },
  });

  guiders.createGuider({
    attachTo: "tr#send-to",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Continue",
      onclick: guiders.next
    }],
    title: "Choose who to share this with",
    description: "- Enter a group names to share with anyone in those groups, or enter names or email addresses to share with specific people<br>- Click \"x\" to delete a group or person",
    onShow: function() {
      disable_scroll();
      $('a#send-to').trigger('click');
    },
    onHide: enable_scroll,
    id: "tour-6",
    next: "tour-7",
    position: 7,
    offset: {
      left: -5,
      top: -30
    }
  });

  guiders.createGuider({
    attachTo: "form#new-feed .button",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Continue",
      onclick: guiders.next
    }],
    description: "Click Share when you're ready to post",
    onShow: disable_scroll,
    onHide: enable_scroll,
    id: "tour-7",
    next: "tour-9",
    position: 9,
    offset: {
      left: 20,
      top: 25
    },
    title: "Ready, set, share!"
  });

  // guiders.createGuider({
    // attachTo: "form#invite input[type='email']",
    // autoFocus: true,
    // buttons: [{
      // name: "Exit Tour",
      // onclick: guiders.hideAll
    // }, {
      // name: "Continue",
      // onclick: guiders.next
    // }],
    // description: "Enter your coworker email addresses to invite them to join Jupo",
    // onShow: disable_scroll,
    // onHide: enable_scroll,
    // id: "tour-8",
    // next: "tour-9",
    // position: 9,
    // offset: {
      // left: 20,
      // top: 26
    // },
    // title: "Invite your coworkers"
  // });

  guiders.createGuider({
    attachTo: "li#reminders > a.async",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Continue",
      onclick: guiders.next
    }],
    title: "Your personal to-to list",
    description: "Quick & easy way to getting things done.",
    onShow: function() {
      disable_scroll();
      $('li#news-feed > a').removeClass('active');
      $('li#reminders > a').addClass('active');
    },
    onHide: function() {
      enable_scroll();
      $('li#reminders > a').removeClass('active');
    },
    id: "tour-9",
    next: "tour-10",
    offset: {
      left: -100,
      top: 27
    },
    position: 3
  });

  guiders.createGuider({
    attachTo: "li#notes > a.async",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Continue",
      onclick: guiders.next
    }],
    title: "Notes",
    description: "Write without fear of losing or overwriting a good idea.",
    onShow: function() {
      disable_scroll();
      $('li#notes > a').addClass('active');
    },
    onHide: function() {
      enable_scroll();
      $('li#notes > a').removeClass('active');
    },
    id: "tour-10",
    next: "tour-11",
    offset: {
      left: -100,
      top: 27
    },
    position: 3
  });

  guiders.createGuider({
    attachTo: "li#files > a.async",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Continue",
      onclick: guiders.next
    }],
    title: "Files & Attachments",
    description: "File with versioning support",
    onShow: function() {
      disable_scroll();
      $('li#files > a').addClass('active');
    },
    onHide: function() {
      enable_scroll();
      $('li#files > a').removeClass('active');
      $('li#news-feed > a').addClass('active');
    },
    id: "tour-11",
    next: "tour-12",
    offset: {
      left: -100,
      top: 27
    },
    position: 3
  });

  guiders.createGuider({
    attachTo: "#groups-nav",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Continue",
      onclick: guiders.next
    }],
    title: "Recent groups",
    description: "foobar",
    onShow: disable_scroll,
    onHide: enable_scroll,
    id: "tour-12",
    next: "tour-13",
    position: 3
  });

  guiders.createGuider({
    attachTo: "#stream li.feed:first-child section > footer a.reply",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Continue",
      onclick: function() {
        $("#stream li.feed:first-child section > footer a.reply").trigger('click');
        guiders.next();
      }
    }],
    title: "Join the conversation",
    description: "- Hover mouse across post to tell other you already read this<br>- Star the things you really love<br>",
    onShow: disable_scroll,
    onHide: enable_scroll,
    id: "tour-13",
    next: "tour-14",
    offset: {
      left: 0,
      top: 30
    },
    position: 11
  });

  guiders.createGuider({
    attachTo: "#stream li.feed:first-child form.new-comment textarea.mention",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Next",
      onclick: guiders.next
    }],
    title: "Real-time commenting",
    description: "- Press Enter to Post<br>- Press Ctrl+Enter for new line<br>- <a>Jupo Flavored Markdown</a> supported",
    onShow: disable_scroll,
    onHide: enable_scroll,
    id: "tour-14",
    next: "tour-15",
    offset: {
      left: 0,
      top: -30
    },
    position: 7
  });

  guiders.createGuider({
    attachTo: "#stream li.feed:first-child form.new-comment a.attach-button",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Next",
      onclick: guiders.next
    }],
    title: "Attach files, pictures and links",
    description: "Click to choose file",
    onShow: disable_scroll,
    onHide: enable_scroll,
    id: "tour-15",
    next: "tour-16",
    offset: {
      left: 0,
      top: -30
    },
    position: 7
  });

  guiders.createGuider({
    attachTo: "#stream div.actions a.archive:first",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Next",
      onclick: guiders.next
    }],
    title: "Archive post",
    description: "Archiving lets you tidy up your stream by hiding posts from your What's new. When someone responds to a post you've archived, the conversation containing that message will reappear in What's new stream.",
    onShow: disable_scroll,
    onHide: enable_scroll,
    id: "tour-16",
    next: "tour-17",
    offset: {
      left: 0,
      top: 25
    },
    position: 11
  });

  guiders.createGuider({
    attachTo: "#stream div.actions a.toggle:first",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Next",
      onclick: guiders.next
    }],
    title: "Pinned post",
    description: "A pinned post always appears in the to of What's new stream",
    onShow: disable_scroll,
    onHide: enable_scroll,
    id: "tour-17",
    next: "tour-18",
    offset: {
      left: 0,
      top: 25
    },
    position: 11
  });

  guiders.createGuider({
    attachTo: "#stream div.options a.viewers:first",
    autoFocus: true,
    buttons: [{
      name: "Exit Tour",
      onclick: guiders.hideAll
    }, {
      name: "Next",
      onclick: guiders.next
    }],
    title: "Control who can see/comment on your post",
    description: "Hover mouse over this icon to show viewers list. Click to change it.",
    onShow: disable_scroll,
    onHide: enable_scroll,
    id: "tour-18",
    next: "tour-19",
    offset: {
      left: 20,
      top: 24
    },
    position: 9
  });

}



function mark_as_read(item_id) {
  $('#body #' + item_id).removeClass('unread').show();
  $('#overlay #' + item_id).removeClass('unread').show();
      
  var request_url = '/feed/' + item_id.replace('post-', '') + '/mark_as_read';
  console.log(request_url);
  $.ajax({
    type: 'POST',
    url: request_url,
    async: true,
    headers: {
      'X-CSRFToken': get_cookie('_csrf_token')
    },
    success: function(resp) {

      console.log('mark as read: Done');
    }
  })
}

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
}

function decr(id, value) {
  var item = $(id);
  var value = typeof (value) != 'undefined' ? value : 1;
  value = parseInt(item.html()) - parseInt(value);
  item.html(value);
  if (value == 0) {
    item.hide();
  }
  
  return value;
}

function get_doc_height() {
  var D = document;
  return Math.max(Math.max(D.body.scrollHeight, D.documentElement.scrollHeight), Math.max(D.body.offsetHeight, D.documentElement.offsetHeight), Math.max(D.body.clientHeight, D.documentElement.clientHeight))
};

(function($) {
  if (get_cookie('channel_id') != null) {

    var timeout = 30000;

    $(document).bind("idle.idleTimer", function() {
      update_status('away');
      console.log("away");
    });

    $(document).bind("active.idleTimer", function() {
      console.log("online");
      update_status('online');
      if ($('a.unread-posts').is(":visible")) {
        $('a.unread-posts').trigger('click');

        $('body').animate({
          scrollTop: 0
        }, 'fast');
      }
    });

    $.idleTimer(timeout);

  }
})(jQuery);









// Server push
function stream() {
  
  var source = new EventSource('/stream');
  
  source.onopen = function(e) {
    var ts = new Date().getTime();
    if ($.global.last_connect_timestamp != undefined && ts - $.global.last_connect_timestamp > 300000) { // 300 seconds = 5 minutes
      window.location.href = window.location.href;
    }
    
    $.global.last_connect_timestamp = ts;
  }
  
  source.onerror = function(e) {
    console.log(e);
    switch (e.target.readyState) {
       case EventSource.CONNECTING:  
          console.log('Reconnecting...');  
          break;
       case EventSource.CLOSED:  
          console.log('Connection failed. Retrying...');
          setTimeout(function() {
            stream();
          }, 5000);  
          break;    
       default:
          console.log('Connection error. Retrying...');
          setTimeout(function() {
            stream();
          }, 5000);  
          break;    
       
    }  
  }
  
  source.onmessage = function(e) {
    var event = window.JSON.parse(e.data);
  
    if (event.type == 'friends-online') {
      user = event.user;
      element = $('ul#friends-online #user-' + user.id);
      
      // Update user status led
      if (user.status.indexOf('|') == -1) {
        $('.user-' + user.id + '-status').removeClass('online offline away').addClass(user.status);
      }
      
      if ((element.length == 0 && user.status == 'online') || user.status == 'offline') {
        
        if (user.status == 'offline') {
          console.log('wait 5 seconds...');
          
          $.global.offline_notification_timer_done = false;
          $.global.offline_notification_timer = setTimeout(function() {
            // show_notification(user.avatar, user.name, 'is ' + user.status, 5000, function() {
              // window.open('/user/' + user.id);
            // })
            $.global.offline_notification_timer_done = true;
          }, 5000)
        } 
        
        else if (user.status == 'online') {
          if ($.global.offline_notification_timer_done == false) {
            console.log('is refresh: not show notification');
            clearTimeout($.global.offline_notification_timer);
            $.global.offline_notification_timer_done = true;
          }
          else {
            $.global.offline_notification_timer_done = true;
            show_notification(user.avatar, user.name, 'is ' + user.status, 5000, function() {
              window.focus();
            })
          }
        }
        
        
      }
          
      $('ul#friends-online #user-' + user.id).remove();
      if (user.status != 'offline') {
        $('ul#friends-online div.online').prepend(event.info);
      }
      
      var online_count = $('#friends-online li.status.online').length + $('#friends-online li.status.away').length;
      $('.online-now .online-count').html(online_count);
      
      if (online_count == 0) {
        $('#friends-online div.empty').removeClass('hidden');
      } else {
        $('#friends-online div.empty').addClass('hidden');
      }
      
      refresh('ul#friends-online');
  
    } else if (event.type == 'unread-notifications') {
      var item = $('#unread-notification-counter');

      var value = parseInt(event.info);
      if (value < 0) {
        value = 0;
      }

      item.html(value);
      if (value != 0) {
        item.show();
      } else {
        item.hide();
      }
  
      var title = document.title;
      var pattern = /^\(.*?\) /gi;
      var count = title.match(pattern);
      if (value != 0) {
        $('#unread-notification-counter').removeClass('grey');
        if (count == null) {
          document.title = '(' + $('#unread-notification-counter').html() + ') ' + title;
        } else {
          document.title = title.replace(count, '(' + $('#unread-notification-counter').html() + ') ');
        }
      } else {
        $('#unread-notification-counter').addClass('grey');
        if (count != null) {
          document.title = title.replace(count, '');
        }
      }
      
   
      
    } else if (event.type == 'typing-status') {
      console.log(event.info);
      var chatbox = $('#chat-' + event.info.chat_id)
      if (chatbox.length != 0) {
        if (event.info.text != '') {
          $('div.status', chatbox).html(event.info.text).fadeIn('fast');
        } else {
          $('div.status', chatbox).fadeOut('fast');
        }
        
        
      }
    } else if (event.type == 'unread-feeds' && window.location.pathname.indexOf('/group/') == -1) {
  
      console.log(event);
  
      var feed_id = $(event.info).attr('id');
      console.log('new: ' + feed_id);
      
      user_id = $('a.async[data-user-id]', $(event.info)).attr('data-user-id');
      owner_id = $('header nav a[data-owner-id]').attr('data-owner-id');
      
          
      if ($.global.disable_realtime_update != feed_id) {
  
        if ($('#' + feed_id).length != 0) {// feed existed.
          // append comment
          // only
                     
                     
  
          var comment = $('div.comments-list li.comment:last-child', $(event.info));
          // var quick_stats = $('.quick-stats', $(event.info));
  
          if (comment.length != 0 && $('#body #' + comment.attr('id')).length == 0) {
            
            
            var offset_top = null;
            var last_comment = $('#' + feed_id + ' li.comment:last');
            
            if (last_comment.length == 0) {
              if ($('#' + feed_id).length != 0) {
                offset_top = $('#' + feed_id).offset().top
              }
              
            } else {
              offset_top = last_comment.offset().top
            }
            
            if (offset_top != null) {
              $('body').scrollTop(offset_top - 250);
            }  
            
            $('#body #' + feed_id + ' ul.comments').removeClass('hidden');
            $('#body #' + feed_id + ' div.comments-list').append(comment.hide().fadeIn('fast'));
            $('#body #' + feed_id).addClass('unread');
            $('#body #' + feed_id + ' li.comment:last-child').addClass('unread');
  
  
          
            // $('#body #' + feed_id + ' .quick-stats').replaceWith(quick_stats);
  
            // update comment counter
            incr('#body #' + feed_id + ' .quick-stats .comment-count', 1);
            incr('#body #' + feed_id + ' .comments-list .comment-count', 1);
  
            // set read-receipts to "No one"
            $('#body #' + feed_id + ' a.quick-stats .receipt-icon').remove();
            $('#body #' + feed_id + ' a.quick-stats .read-receipts-count').remove();
            $('#body #' + feed_id + ' li.read-receipts').html('<i class="receipt-icon"></i> Seen by no one.');
  
            // Update overlay post
            $('#overlay #' + feed_id + ' ul.comments').removeClass('hidden');
            $('#overlay #' + feed_id + ' div.comments-list').append(comment.hide().fadeIn('fast'));
            $('#overlay #' + feed_id).addClass('unread');
            $('#overlay #' + feed_id + ' li.comment:last-child').addClass('unread');
  
            // $('#overlay #' + feed_id + '
            // .quick-stats').replaceWith(quick_stats);
  
            // update comment counter
            incr('#overlay #' + feed_id + ' .quick-stats .comment-count', 1);
            incr('#overlay #' + feed_id + ' .comments-list .comment-count', 1);
  
            $('#overlay #' + feed_id + ' a.quick-stats .receipt-icon').remove();
            $('#overlay #' + feed_id + ' a.quick-stats .read-receipts-count').remove();
            $('#overlay #' + feed_id + ' li.read-receipts').html('<i class="receipt-icon"></i> Seen by no one.');
  
            refresh('#body #' + feed_id);
            // refresh timeago
            refresh('#overlay #' + feed_id);
            // refresh timeago
            
            
            msg = $('.message .text', comment).html().replace(/\s\s+/, ' ').slice(0, 50);
            username = $('.message strong', comment).html();
            avatar = $('img.small-avatar', comment).attr('src');
            
                  
            // Không hiện thống báo khi post là do mình gửi
            if (user_id != owner_id) {
              
                  show_notification(avatar, username, msg, 10000, function() {
                    // window.open('/post/' + feed_id.split('-')[1] + '#' + comment.attr('id'), '_blank', 'width=550px,height=300,resizable=0,alwaysRaised=1,location=0,links=0,scrollbars=0,toolbar=0')
                    window.focus();
                  })
            }
      
              
              
            
            // $.noticeAdd({text: '<a href="#' + feed_id + '" class="scroll">1 new comment</a>', stay: true})
            
          }
  
  
        
  
  
        } else {
          $('ul#stream').prepend(event.info);
          
          // $.noticeAdd({text: '<a href="#' + feed_id + '" class="scroll">1 new post</a>', stay: true})
          
          // $('#body #' + feed_id + ' ul.comments').removeClass('hidden');
  
          if ($.global.status == 'online') {
            $('ul#stream > li.hidden').addClass('unread').fadeIn();
          } else {
            incr("#unread-counter", 1);
            $('div#unread-messages').fadeIn();
          }
          refresh('ul#stream li:first');
          
          $('body').scrollTop(0);
        }
        setTimeout(function() {
          $.global.disable_realtime_update = null;
        }, 50);
      } else {
        $.global.disable_realtime_update = null;
      }
      
          
    } else if (event.type && event.type.indexOf('unread-feeds') != -1) {
  
      if (event.type.indexOf('|') != -1) {
        
        
        var group_id = event.type.split('|')[0];
        incr('#group-' + group_id + ' span.count');
        
        if (window.location.pathname.indexOf(group_id) != -1) {
          var feed_id = $(event.info).attr('id');
          if ($.global.disable_realtime_update != feed_id) {
            
  
            if ($('#' + feed_id).length) {// feed existed. append comment only
  
              var comment = $('div.comments-list li:last-child', $(event.info));
              // var quick_stats = $('.quick-stats', $(event.info));
  
              if (comment.length != 0 && $('#' + comment.attr('id')).length == 0) {
                
                var offset_top = null;
                var last_comment = $('#' + feed_id + ' li.comment:last');
                
                if (last_comment.length == 0) {
                  if ($('#' + feed_id).length != 0) {
                    offset_top = $('#' + feed_id).offset().top
                  }
                  
                } else {
                  offset_top = last_comment.offset().top
                }
                
                if (offset_top != null) {
                  $('body').scrollTop(offset_top - 250);
                }                
                
                $('#body #' + feed_id + ' ul.comments').removeClass('hidden');
                $('#body #' + feed_id + ' div.comments-list').append(comment.hide().fadeIn('fast'));
                $('#body #' + feed_id).addClass('unread');
                $('#body #' + feed_id + ' li.comment:last-child').addClass('unread');
  
                // $('#body #' + feed_id + '
                // .quick-stats').replaceWith(quick_stats);
  
                // update comment counter
                incr('#body #' + feed_id + ' .quick-stats .comment-count', 1);
                incr('#body #' + feed_id + ' .comments-list .comment-count', 1);
  
                // remove read-receipts
                $('#body #' + feed_id + ' a.quick-stats .receipt-icon').remove();
                $('#body #' + feed_id + ' a.quick-stats .read-receipts-count').remove();
                $('#body #' + feed_id + ' li.read-receipts').html('<i class="receipt-icon"></i> Seen by no one.');
  
                // Update overlay post
                $('#overlay #' + feed_id + ' ul.comments').removeClass('hidden');
                $('#overlay #' + feed_id + ' div.comments-list').append(comment.hide().fadeIn('fast'));
                $('#overlay #' + feed_id).addClass('unread');
                $('#overlay #' + feed_id + ' li.comment:last-child').addClass('unread');
  
                // $('#overlay #' + feed_id + '
                // .quick-stats').replaceWith(quick_stats);
  
                // update comment counter
                incr('#overlay #' + feed_id + ' .quick-stats .comment-count', 1);
                incr('#overlay #' + feed_id + ' .comments-list .comment-count', 1);
  
                $('#overlay #' + feed_id + ' a.quick-stats .receipt-icon').remove();
                $('#overlay #' + feed_id + ' a.quick-stats .read-receipts-count').remove();
                $('#overlay #' + feed_id + ' li.read-receipts').html('<i class="receipt-icon"></i> Seen by no one.');
  
                refresh('#body #' + feed_id);
                // refresh timeago
                refresh('#overlay #' + feed_id);
                // refresh timeago
              }
              
  
            } else {
              $('ul#stream').prepend(event.info);
  
              if ($.global.status == 'online') {
                $('ul#stream > li.hidden').addClass('unread').fadeIn();
              } else {
                $('span#unread').html($('ul#stream > li.hidden').length);
                $('div#unread-messages').fadeIn();
              }
              refresh('ul#stream li:first');
              
              $('body').scrollTop(0);
            }
  
            setTimeout(function() {
              $.global.disable_realtime_update = null;
            }, 50);
          } else {
  
            $.global.disable_realtime_update = null;
          }
        }
      }
  
    } else if (event.type == 'read-receipts') {
      
      var text = event.info.text;
      var post_id = event.info.post_id;
      var quick_stats = event.info.quick_stats;
      var viewers = event.info.viewers;
      
      // Update group unread counter
      if (viewers && text.indexOf('Seen by you') != -1) {
        $.each(viewers, function (index, group_id) {
          console.log('#group-' + group_id + ' span.count');
          decr('#group-' + group_id + ' span.count');
        })
      }
      
  
      $.global._tmp = event;
  
      $('div#body #post-' + post_id + ' a.quick-stats span.read-receipts').html(quick_stats);
      $('div#overlay #post-' + post_id + ' a.quick-stats span.read-receipts').html(quick_stats);
      
      if (quick_stats.indexOf('>0<') == -1) {
        $('div#body #post-' + post_id + ' a.quick-stats span.read-receipts').removeClass('hidden');
      } else {
        $('div#body #post-' + post_id + ' a.quick-stats span.read-receipts').addClass('hidden'); 
      }

      $('div#overlay #post-' + post_id + ' a.quick-stats').attr('title', text);
      $('div#body #post-' + post_id + ' a.quick-stats').attr('title', text);
      
      $('div#overlay #post-' + post_id + ' a.remove-comment').remove();
      $('div#body #post-' + post_id + ' a.remove-comment').remove();
  
      $('div#overlay #post-' + post_id + ' ul.menu a.remove').parent().remove();
      $('div#body #post-' + post_id + ' ul.menu a.remove').parent().remove();
  
    } else if (event.type == 'likes' ) {
      var html_code = event.info.html;
      var post_id = event.info.post_id;
      var quick_stats = event.info.quick_stats;
  
      $('div#body #post-' + post_id + ' a.quick-stats span.likes').html(quick_stats);
      if (quick_stats.indexOf('>0<') == -1) {
        $('div#body #post-' + post_id + ' a.quick-stats span.likes').removeClass('hidden');
      } else {
        $('div#body #post-' + post_id + ' a.quick-stats span.likes').addClass('hidden'); 
      }
          
      $('div#overlay #post-' + post_id + ' li.likes').remove();
      $('div#body #post-' + post_id + ' li.likes').remove();
  
      $('div#overlay #post-' + post_id + ' div.comments-list').prepend(html_code);
      $('div#body #post-' + post_id + ' div.comments-list').prepend(html_code);

    } else if (event.type == 'like-comment') {
      
      $('#comment-' + event.info.comment_id + ' .likes .counter').html(event.info.likes_count);
      
      if (event.info.likes_count == 0) {
        $('#comment-' + event.info.comment_id + ' .likes').addClass('hidden')
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
        $('#post-' + event.info.post_id).remove();
      }
      
    } else if (event.type == 'update') {
      if (event.info.comment_id) {
        $('#comment-' + event.info.comment_id + ' div.message .text:not(.hidden)').html(event.info.text);
        $('#comment-' + event.info.comment_id + ' div.message .text.hidden').html(event.info.changes);
        $('#comment-' + event.info.comment_id + ' a.see-changes').attr('original-title', 'Click to see changes');
      }
      

    }
    
    else if (event.type == 'seen-by') {
      var msg = event.info.html;
      var chat_id = event.info.chat_id;
      
      $('#chat-' + chat_id + ' div.status').html(msg).fadeIn('fast');
    }
    
    else if (event.type == 'new-message') {
      var msg = event.info.html;
            
      var _msg = msg;
      var msg = $(msg);
      
      var sender_id = msg.attr('data-sender-id');
      var receiver_id = msg.attr('data-receiver-id');
      var topic_id = msg.attr('data-topic-id');
      
      var owner_id = $('header #menu a[data-owner-id]').attr('data-owner-id');
      
      if (topic_id != undefined) {
        chat_id = 'topic-' + topic_id;
      } 
      else if (sender_id == owner_id) {
        chat_id = 'user-' + receiver_id;
      } 
      else {
        chat_id = 'user-' + sender_id;
      }
      
      if (sender_id != owner_id) {
        if ($('#chat-' + chat_id + ' textarea._elastic').is(':focus') == false) {
          $('#chat-' + chat_id).addClass('unread');  
        } 
        
        
        var username = $('a.async[title]', msg).attr('title');
        var avatar = $('a.async[title] img.small-avatar', msg).attr('src');
        var message_content = $('div.content', msg).html();
        
        // flashing message in the browser title bar
        $.titleAlert(username + " messaged you", {
            requireBlur: true,
            stopOnFocus: true,
            duration: 0,
            interval: 2000
        });
        
        // show desktop notification
        show_notification(avatar, username, message_content, 5000, function() {
          window.focus();
        })
        
      }
      
      
      if ($('#chat-' + chat_id).length == 0) {
        start_chat(chat_id);
      }
      
      var boxchat = $('#chat-' + chat_id);
      var last_msg = $('li.message:last', boxchat);

      var msg_id = msg.attr('id').split('-')[1];
      var msg_ts = msg.data('ts');
      var sender_id = msg.attr('data-sender-id');
      
      if (msg_ts - last_msg.data('ts') < 120 && last_msg.attr('data-sender-id') == sender_id) {
        if (last_msg.attr('data-msg-ids').indexOf(msg_id) == -1) {
          var content = $('.content', msg).html();
          $('.content', last_msg).html($('.content', last_msg).html() + '<br>' + content);
          $(last_msg).data('ts', msg_ts);
          $(last_msg).attr('data-msg-ids', $(last_msg).attr('data-msg-ids') + ',' + msg_id);
        }
      } else {
        $('.messages', boxchat).append(_msg);
      }
      
      $('div.status', boxchat).fadeOut('fast');
      
      setTimeout(function() {
        $('.messages', boxchat).scrollTop(99999);
      }, 10)  

    }
    
    else {
      console.log(event);
    }
    
  };
}






function open_in_async_mode(href, rel, data, f) {
  
  hide_searchbox_dropdown();
  close_popup();
 
  $('header nav ul.dropdown-menu').addClass('hidden');
  $('header nav .dropdown-menu-active').removeClass('dropdown-menu-active');
  

  // Destroy all plupload
  for (var i in $.global)
    if ($.global.hasOwnProperty(i) && i.indexOf('uploader_') != -1) {
      try {
        $.global[i].destroy();
        delete $.global[i];
      } catch (err) {}
    }

  if ($.global.request != undefined) {
    $.global.request.abort();
    console.log('aborted');
  }
  
  if (href.indexOf('#!') != -1) {
    var href = href.split('#!')[1];
  }
  parts = href.split('#');
  if (parts.length >= 2 && parts[1] == 'comments') {
    // scroll_to = 'div#overlay ul.comments';
    scroll_to = 'div#body form.new-comment';
  } else if (parts.length >= 2 && parts[1] == 'diff') {
    scroll_to = 'div#body span.diff';
  } else {
    scroll_to = null;
  }

  if (data) {

    resp = $.parseJSON(data);

    if (resp.title) {
      update_title(resp.title)
    }

    if (rel) {
      $(".current ul").remove();

      $(".current").removeClass("current");

      $("#left-sidebar .active").addClass("async");
      $("#left-sidebar .active").removeClass("active");
      parent_id = '#' + rel;
      $(parent_id).html(resp.menu);
      $(parent_id).addClass("current");
      $(parent_id).removeClass("async");
    }
    

    $('body').animate({
        scrollTop: 0
    }, 'fast');
  
    if ($("#body").is(":visible")) {
      $("#body").queue(function(next) {
        $(this).attr('class', 'animate fadeOut'); 
        next();
      }).delay(100).queue(function(next) {
        $(this).html(resp.body);
        $(this).attr('class', 'animate fadeIn').show();
        next();
      })
    } else {
      $("#overlay").queue(function(next) {
        $(this).attr('class', 'animate fadeOut'); 
        next();
      }).delay(100).queue(function(next) {
        $('#overlay').hide().attr('class', '');
        $('#body').html(resp.body);
        $('#body').attr('class', 'animate fadeIn').show();
        next();
      })
    }
    
    refresh('#body');
    
    if (scroll_to != null) {
      setTimeout(function() {
        offset_top = $(scroll_to).offset().top - 45;
        console.log('offset top: ' + offset_top);
        $('html,body').animate({
          scrollTop: offset_top
        }, 'fast');
      }, 150);
    }

    // Remove data of last overlay
    $("#overlay").html("");
    $("#overlay").hide();
    $.global.body = null;
    $.global.scroll = null;

  } else {

    show_loading();
    $.global.request = $.ajax({
      type: "OPTIONS",
      url: href,
      dataType: "json",
      error: function(jqXHR, textStatus, errorThrown) {
        if (textStatus != 'abort') {
          show_error();
        }
      },
      success: function(resp) {
        
        if (resp == null) {
          show_error();
          return false;
        }        

        if ($.global.history.length == 10) {
          key = $.global.history.pop();
          sessionStorage.removeItem(key);
          console.log('Remove ' + key + ' from Session Storage');
        }

        sessionStorage[href] = JSON.stringify(resp);
        // save to session storage (for Back button)
        $.global.history.unshift(href);

        hide_loading();

        history.pushState({
          rel: rel,
          path: href
        }, resp.title, href);
        // change URL in browser (if support HTML5)

        if (resp.title) {
          update_title(resp.title);
        }

        if (rel) {
          $(".current ul").remove();

          $(".current").removeClass("current");

          $("#left-sidebar .active").addClass("async");
          $("#left-sidebar .active").removeClass("active");
          parent_id = '#' + rel;
          $(parent_id).html(resp.menu);
          $(parent_id).addClass("current");
          $(parent_id).removeClass("async");
          
        }
   
        
        if ($("#body").is(":visible")) {
          $("#body").queue(function(next) {
            $(this).attr('class', 'animate fadeOut'); 
            next();
          }).delay(100).queue(function(next) {
            $(this).html(resp.body);
            
            
            setTimeout(function() {
              refresh('#body');
            }, 200);
            
            $(this).attr('class', 'animate fadeIn').show();
            next();
          })
        } else {
          $("#overlay").queue(function(next) {
            $(this).attr('class', 'animate fadeOut'); 
            next();
          }).delay(100).queue(function(next) {
            $('#overlay').hide().attr('class', '');
            $('#body').html(resp.body);
            
            setTimeout(function() {
              refresh('#body');
            }, 200);
            
            
            $('#body').attr('class', 'animate fadeIn').show();
            next();
          })
        }

    
        
        $('body').animate({
            scrollTop: 0
        }, 'fast');
        
        // Remove data of last overlay
        $("#overlay").html("");
        $("#overlay").hide();
        $.global.body = null;
        $.global.scroll = null;

        
        if (scroll_to != null) {
          setTimeout(function() {
            offset_top = $(scroll_to).offset().top - 45;
            console.log('offset top: ' + offset_top);
            $('html,body').animate({
              scrollTop: offset_top
            }, 'fast');
          }, 150);
        }



        // callback
        if (typeof f == "function") f();
      }
    });
  }
  
  return false;
}

function open_in_popup_mode(href, data) {
    if ($.global.request != undefined) {
      $.global.request.abort();
    }
    
    hide_searchbox_dropdown();
    show_loading();

    $.global.request = $.ajax({
      type: "OPTIONS",
      url: href,
      dataType: "json",
      error: function(jqXHR, textStatus, errorThrown) {
        if (textStatus != 'abort') {
          show_error();
        }
      },
      success: function(resp) {
        hide_loading();
        $('html').addClass('no-scroll');
        $('#popup .content').html(resp.body);
        $('#popup').removeClass('hidden');
        refresh('#popup');
        return false;
      }
    })
    return false;
}

function open_in_overlay_mode(href, data) { // has #! in url
  
  // Hide all dropdowm menus
  hide_searchbox_dropdown();
  $('a.dropdown-menu-icon.active').parent().removeClass('active');
  $('a.dropdown-menu-icon.active').next('ul').hide();
  $('a.dropdown-menu-icon.active').removeClass('active');
  
  $('header nav ul.dropdown-menu').addClass('hidden');
  $('header nav .dropdown-menu-active').removeClass('dropdown-menu-active');

  // Save current scrolling position
  $.global.scroll = $("body").scrollTop();

  if (href.indexOf('#!') != -1) {
    var href = href.split('#!')[1];
  }
  parts = href.split('#');
  if (parts.length >= 2 && parts[1] == 'comments') {
    // scroll_to = 'div#overlay ul.comments';
    scroll_to = 'div#overlay form.new-comment';
  } else if (parts.length >= 2 && parts[1] == 'diff') {
    scroll_to = 'div#overlay span.diff';
  } else {
    scroll_to = null;
  }

  if (data) {
    resp = $.parseJSON(data);

    if (resp.title) {
      $.global.title = document.title;
      update_title(resp.title);
    }

    // Show close button and tooltip at top right cornor
    // resp.body += "<a id='close' class='close-icon' onclick='close_overlay();'></a>";
    // resp.body = "<span id='hint'>Press ESC to close</span>" + resp.body;
    

    $('body').animate({
        scrollTop: 0
    }, 'fast');
  
    $('#overlay').html(resp.body);
    refresh('#overlay');
  
    if ($('#body').is(':visible')) {
      $("#body").queue(function(next) {
        $(this).attr('class', 'animate fadeOut'); 
        next();
      }).delay(100).queue(function(next) {
        $(this).hide();
        $('#overlay').attr('class', 'animate fadeIn').show();
        next();
      })
    } else {
      $("#overlay").queue(function(next) {
        $(this).attr('class', 'animate fadeOut'); 
        next();
      }).delay(100).hide().queue(function(next) {
        $(this).attr('class', 'animate fadeIn').show();
        next();
      })
    }
      

    if (scroll_to != null) {
      setTimeout(function() {
        offset_top = $(scroll_to).offset().top - 45;
        console.log('offset top: ' + offset_top);
        $('html,body').animate({
          scrollTop: offset_top
        }, 'fast');
      }, 50);
    }

  } else {

    if ($.global.request != undefined) {
      $.global.request.abort();
    }

    show_loading();

    $.global.request = $.ajax({
      type: "OPTIONS",
      url: href,
      dataType: "json",
      error: function(jqXHR, textStatus, errorThrown) {
        if (textStatus != 'abort') {
          show_error();
        }
      },
      success: function(resp) {
        close_popup();

        href = '#!' + href;

        if ($.global.history.length == 10) {
          key = $.global.history.pop();
          sessionStorage.removeItem(key);
          console.log('Remove ' + key + ' from Session Storage');
        }

        sessionStorage[href] = JSON.stringify(resp);
        // save to session storage (for Back button)
        $.global.history.unshift(href);

        hide_loading();

        if (resp == null) {
          show_error();
          return false;
        }

        history.pushState({
          rel: null,
          path: href
        }, 'Jupo', href);
        // change URL in browser (if support HTML5)

        if (resp.title) {
          $.global.title = document.title;
          update_title(resp.title);
        }

        if (resp.unread_notifications_count != undefined) {
          var item = $('#unread-notification-counter');
       
          value = parseInt(resp.unread_notifications_count);

          item.html(value);
          if (value != 0) {
            item.show();
          } else {
            item.hide();
          }
        }

        // Show close button and tooltip at top right cornor
        // resp.body += "<a id='close' class='close-icon' onclick='close_overlay();'></a>";
        // resp.body = "<span id='hint'>Press ESC to close</span>" + resp.body;
        

        $('body').animate({
            scrollTop: 0
        }, 'fast');
  
        $('#overlay').html(resp.body);
        refresh('#overlay');
        
        if ($('#body').is(':visible')) {
          $("#body").queue(function(next) {
            $(this).attr('class', 'animate fadeOut'); 
            next();
          }).delay(100).queue(function(next) {
            $(this).hide();
            $('#overlay').attr('class', 'animate fadeIn').show();
            next();
          })
        } else {
          $("#overlay").queue(function(next) {
            $(this).attr('class', 'animate fadeOut'); 
            next();
          }).delay(100).hide().queue(function(next) {
            $(this).attr('class', 'animate fadeIn').show();
            next();
          })
        }

        if (scroll_to != null) {
          setTimeout(function() {
            offset_top = $(scroll_to).offset().top - 45;
            console.log('offset top: ' + offset_top);
            $('html,body').animate({
              scrollTop: offset_top
            }, 'fast');
          }, 50);
        }

      }
    });
  }

  return false;
}

function close_popup() {
  $('#popup').addClass('hidden');
      $('#popup .content').html('');
      
        $('html').removeClass('no-scroll');
}

function close_overlay() {

  $('#overlay').queue(function(next) {
    $(this).attr('class', 'animate fadeOut');
    next();
  })
  .delay(200)
  .queue(function(next) {
    $(this).empty().attr('class', '').hide();
    $("#body").attr('class', 'animate fadeIn').show();
    next();
  });
  

  // $('body').animate({
          // scrollTop: $.global.scroll
        // }, 'fast');
  
  
  $.global.scroll = null;

  hide_searchbox_dropdown();

  // clear hashbang in url
  history.pushState({
    rel: null,
    path: window.location.pathname
  }, 'Jupo', window.location.pathname);
  // change URL in browser (if
  // support HTML5)

  if ($.global.title) {
    update_title($.global.title);
  }
}

function refresh(element) {
  preload_autocomplete();

  $('div.tipsy').remove();
  
  $(element + " .post-stats a.async").tipsy({
    gravity: 's',  
    live: true
  });

  $(element + " img.medium-avatar, img.small-avatar, img.micro-avatar").fixBroken();
  
  
  // remove custome style (in email) if exists
  $(element + ' .email .body style').empty(); 
  
  // make external links open to new tabs
  $(element + ' a[href^="http://"]:not(.button)').attr('target','_blank');
  $(element + ' a[href^="https://"]:not(.button)').attr('target','_blank');

  $(element + ' ul.comments:not(".hidden") div.comments-list li.comment:last-child').addClass('unread');
  
  
  // Update lại link avatar ở các post đã cache
  var owner_id = $('#menu a.user').attr('data-owner-id');
  var avatar_url = $('#menu a.user img').attr('src');
  $(element + ' a[data-user-id="' + owner_id + '"] img').attr('src', avatar_url);
  
  
  // sửa lại avatar của user trong ô gõ comment (feed có thể bị cache nên cần update lại)
  // avatar_url = $('#menu a.user img').attr('src');
  // user_url = $('#menu a.profile').attr('href');
  // $('form.new-comment a.async:first-child').attr('href', user_url);
  // $('form.new-comment img.small-avatar').attr('src', avatar_url);
  

  if ($.global.timer) {
    console.log('clear timer');
    clearTimeout($.global.timer);
  }

  // Only init tokenInput if not exists
  if ($(element + ' ul.token-input-list').length == 0) {

    var prefill = $(element + ' input.autocomplete').data('prefill');
    if (prefill) {
      prefill = eval(prefill);
    } else {
      prefill = [];
    }

    $(element + ' input.autocomplete:not(.tags)').tokenInput('/autocomplete', {
      searchDelay: 300,
      preventDuplicates: true,
      queryParam: 'query',
      hintText: 'Add people or group...',
      animateDropdown: false,
      resultsFormatter: function(item) {
        return "<li><img class='" + item.type + "' src='" + item.avatar + "'>" + item.name + "</li>"
      },
      prePopulate: prefill,
      allowEmail: true,
      noResultsText: null,
      searchingText: null,
    });

  };

  $(element + ' textarea.mention').mentionsInput({
    minChars: 1,
    fullNameTrigger: false,
    onDataRequest: function(mode, query, callback) {
      search_mentions(query, callback)
    }
  });

  $(element + " time.timeago[datetime!='']").timeago();

  // $(element + ' input.datetime').datetimeEntry({
    // datetimeFormat: 'w, N Y - H:Ma',
    // ampmNames: ['am', 'pm'],
    // useMouseWheel: true,
    // defaultDatetime: "+1d",
    // minDatetime: "+15m",
    // maxDatetime: "+1y",
    // timeSteps: [1, 10, 0],
    // spinnerImage: "",
    // altField: '#isoDatetime',
    // altFormat: 'Y-O-DTH:M:S'
  // });

  // press of the TAB button or SHIFT+TAB to indent or outdent your code.
  // $(element + ' textarea').tabby({
    // tabString: '    '
  // });

  /* Upload */

  try {
    $.global.uploader.destroy();
  } catch (err) {
  }

  try {
    $.global.uploader = new plupload.Uploader({
      runtimes: 'html5',
      browse_button: 'pickfiles',
      container: 'container',
      url: '/attachment/new',
      multi_selection: false,
      // drop_element: 'intro',
      max_file_size: '100mb',
      headers: {
        'X-CSRFToken': get_cookie('_csrf_token')
      }
    });

    $.global.uploader.bind('Init', function(up, params) {
      // $('#filelist').html("<div>Current runtime: " + params.runtime
      // + "</div>");
    });
    $.global.uploader.init();

    $.global.uploader.bind('FilesAdded', function(up, files) {
      $.each(files, function(i, file) {
        $('#filelist').prepend('<div id="' + file.id + '"></div>');
      });

      $.global.uploader.start();
    });

    $.global.uploader.bind('UploadProgress', function(up, file) {
      if (file.percent != 100) {
        $('#body > form.new .upload-status').html("Uploading " + file.percent + "%");
      } else {
        $('#body > form.new .upload-status').html("Verifying...");
      }
    });

    $.global.uploader.bind('Error', function(up, err) {
      $('#' + file.id).hide();
      notify("Error: " + err.code + ", Message: " + err.message + (err.file ? ", File: " + err.file.name : ""));

    });

    $.global.uploader.bind('FileUploaded', function(up, file, response) {
      $('#body > form.new .upload-status').html("");
      
      $('#' + file.id).hide();
      response = $.parseJSON(response.response)

      if ($('div#attachments div#attachment-' + response.attachment_id).length == 0) {
        $('div#attachments').append(response.html);

        files = $('input[name="attachments"]').val() + response.attachment_id + ','
        $('input[name="attachments"]').val(files);

        refresh('div#attachments');
      }

    });
  } catch (err) {
  }

  // Store textarea & input text/email using html5 localstorage

  if ( typeof (Storage) !== "undefined") {
    $('form textarea.mention').each(function() {

      // Build unique id
      var id = null;

      if (window.location.href.indexOf('#!') != -1) {
        url = window.location.hash;
      } else {
        url = window.location.href;
      }

      if ($(this).parents('section').parents('li').length) {
        id = 'li#' + $(this).parents('section').parents('li').attr('id') + ' ';
      } else {
        id = url + '|';
      }

      var form = $(this).parents('form');
      var form_id = form.attr('id');
      id = id + 'form#' + form.attr('id') + ' ' + $(this)[0].nodeName;

      if ($(this).attr('name') != undefined) {
        id += '[name="' + $(this).attr('name') + '"]';
      } else {
        id = id + '.mention:visible';
      }

      if ( typeof $.global.clear_autosave == "undefined") {
        $.global.clear_autosave = {};
      }

      if ( typeof $.global.clear_autosave[url] != "undefined" && $.global.clear_autosave[url] == form_id) {
        $(this).val('');
        // if ($(this).hasClass('watermark')) {
          // $(this).watermark('', {
            // fallback: false,
            // top: 2
          // });
        // }
        // $(this).elastic();
        localStorage.removeItem(id);

        // remove array value
        $.global.clear_autosave[url] = null;

      } else {
        content = localStorage.getItem(id);

        if (content !== null) {
          $(this).val(content);
          // $(this).elastic();
        } else {
          // Watermark content area
          // if ($(this).hasClass('watermark')) {
            // $(this).watermark('', {
              // fallback: false,
              // top: 2
            // });
          // }
        }

        $(this).bind('keyup focusout', function() {
          text = $(this).val();
          if (text.replace(/^\s+|\s+$/g, '') == '') {
            localStorage.removeItem(id);
          } else {
            localStorage[id] = text;
          }
        });

      }
    })
  }

  // End of localstorage
  
  
  if (window.location.href.indexOf('/user/') != -1 && $(element + ' form.new textarea.mention._elastic').length == 1) {
    $(element + ' form.new textarea.mention._elastic').focus();
  }

}



$.fn.fixBroken = function() {
  return this.each(function() {
    var tag = $(this);
    var alt_img = '/public/images/user2.png';
    tag.error(function() {// this adds the onerror event to images
      tag.attr("src", alt_img);
      // change the src attribute of the image
      return true;
    });
  });
};

JSON.stringify = JSON.stringify ||
function(obj) {
  var t = typeof (obj);
  if (t != "object" || obj === null) {
    // simple data type
    if (t == "string")
      obj = '"' + obj + '"';
    return String(obj);
  } else {
    // recurse array or object
    var n, v, json = [], arr = (obj && obj.constructor == Array);
    for (n in obj) {
      v = obj[n];
      t = typeof (v);
      if (t == "string")
        v = '"' + v + '"';
      else if (t == "object" && v !== null)
        v = JSON.stringify(v);
      json.push(( arr ? "" : '"' + n + '":') + String(v));
    }
    return ( arr ? "[" : "{") + String(json) + ( arr ? "]" : "}");
  }
};

function readableFileSize(size) {
  var units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  var i = 0;
  while (size >= 1024) {
    size /= 1024; ++i;
  }
  return size.toFixed(1) + units[i];
}

jQuery.fn.fadeThenSlideToggle = function(speed, easing, callback) {
  if (this.is(":hidden")) {
    return this.slideDown(speed, easing).fadeTo(speed, 1, easing, callback);
  } else {
    return this.fadeTo(speed, 0, easing).slideUp(speed, easing, callback);
  }
};

function get_parameter_by_name(name) {
  name = name.replace(/[\[]/, "\\\[").replace(/[\]]/, "\\\]");
  var regexS = "[\\?&]" + name + "=([^&#]*)";
  var regex = new RegExp(regexS);
  var results = regex.exec(window.location.search);
  if (results == null)
    return "";
  else
    return decodeURIComponent(results[1].replace(/\+/g, " "));
}

function show_error() {
  $('#error').fadeIn(100).delay(10000).fadeOut(100);
  hide_loading();
}

function hide_error() {
  $('#error').fadeOut();
}


function show_loading() {
  $('.loading-bezel').removeClass('hidden').addClass('animate popin')
}

function hide_loading() {
  $('.loading-bezel').addClass('animate popout').delay(200).queue(function(next) {
    $(this).removeClass('animate popin popout').addClass('hidden')
    next();
  })
}

/*
function show_loading() {
  hide_error();

  var loading = $('#loading');
  if (loading.is(':visible')) {
    return false;
  }

  $('#loading').fadeIn(10);

  $.global.loading_interval = setInterval(function() {
    var loading_text = $('span', loading).html();
    if (loading_text.indexOf('...') != -1) {
      $('span', loading).html(loading_text.replace('...', ''));
    } else {
      loading_text += '.';
      $('span', loading).html(loading_text);
    }
  }, 500);
}*/

function show_progress(message) {
  $('#progress').html(message).show();
}

function hide_progress() {
  $('#progress').fadeOut('fast');
}

/*
function hide_loading() {
  var loading = $('#loading');
  var loading_text = $('span', loading).html();

  loading.fadeOut(10);

  $('span', loading).html('Loading...');

  clearInterval($.global.loading_interval);

}*/

jQuery.fn.scroll_to_top = function(settings) {
  settings = jQuery.extend({
    min: 1,
    fadeSpeed: 200
  }, settings);
  return this.each(function() {
    // listen for scroll
    var el = $(this);
    el.hide();
    // in case the user forgot
    $(window).scroll(function() {

      if ($(window).scrollTop() >= settings.min) {
        el.fadeIn(settings.fadeSpeed);
      } else {
        el.fadeOut(settings.fadeSpeed);
      }
    });
  });
};

function isScrolledIntoView(elem) {
  var docViewTop = $(window).scrollTop();
  var docViewBottom = docViewTop + $(window).height();

  var elemTop = $(elem).offset().top;
  var elemBottom = elemTop + $(elem).height();

  // return ((elemBottom >= docViewTop) && (elemTop <= docViewBottom));
  return ((docViewTop < elemTop) && (docViewBottom > elemBottom));
}

function update_status(status, async) {
  var async = typeof (async) != 'undefined' ? async : true;
  if ($.global.status != status) {
    $.global.status = status;
    $.ajax({
      type: 'POST',
      headers: {
        'X-CSRFToken': get_cookie('_csrf_token')
      },
      url: '/set?status=' + status,
      async: async,
      error: function(xhr, ajaxOptions, thrownError) {
        if (xhr.status == 401 && $('section header .viewers .public-icon').length == 0) {
          window.location.href = "/?message=Signed out from remote machine";
        }
      },
      success: function(resp) {
        console.log('request sent.')
      }
    })
  }

}



function start_pingpong() {
  $.global.pingpong = setInterval(function() {
    $.get('/ping', function(resp) {
      console.log(resp)
    })
  }, 60000)
}


function init_avatar_uploader() {
    $.global.avatar_uploader = new plupload.Uploader({
      runtimes: 'html5',
      browse_button: 'pick-avatar',
      container: 'container',
      url: '/attachment/new',
      multi_selection: false,
      max_file_size: '10mb',
      headers: {
        'X-CSRFToken': get_cookie('_csrf_token')
      }
    });

    $.global.avatar_uploader.bind('Init', function(up, params) {});
    $.global.avatar_uploader.init();

    $.global.avatar_uploader.bind('FilesAdded', function(up, files) {
      $.global.avatar_uploader.start();
      show_loading();
    });

    $.global.avatar_uploader.bind('UploadProgress', function(up, file) {
      if (file.percent != 100) {
        console.log("Uploading " + file.percent + "%");
      } else {
        console.log("Verifying...");
      }
    });

    $.global.avatar_uploader.bind('Error', function(up, err) {
      show_error();
    });

    $.global.avatar_uploader.bind('FileUploaded', function(up, file, response) {
      response = $.parseJSON(response.response)
      
      $.ajax({
        type: 'POST',
        headers: {
          'X-CSRFToken': get_cookie('_csrf_token')
        },
        url: '/update_profile_picture?fid=' + response.attachment_id,
        success: function(resp) {
          window.location.href = '/';
        }
      })

    });
}