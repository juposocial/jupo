
  
function open_custom_url_in_iframe(src) {
  var rootElm = document.documentElement;
  var newFrameElm = document.createElement("iframe");
  newFrameElm.setAttribute("src", src);
  rootElm.appendChild(newFrameElm);
  newFrameElm.parentNode.removeChild(newFrameElm);
}


function reload() {
  $.ajax({
    type: 'OPTIONS',
    async: true,
    url: window.location.href,
    success: function(data) {
      $('body > ul.stream').html(data);
      
      refresh();
      
      $('body').animate({scrollTop: 0}, 100, 'swing', function() { 
         console.log("Finished animating");
      });
      
      open_custom_url_in_iframe('jupo://hide_loading_indicator');
      console.log('refresh: done');
    }
  });
  return true;
  
}

function refresh() {
  
  // Disable embeded youtube videos
  $('section iframe').remove();
}


$(document).ready(function() {
  
  refresh();
  
  $('body').on('touchstart', 'a', function(e){
    $(this).addClass('tapped');
  });
  
  $('body').on('touchend', 'a', function(e){
    $(this).removeClass('tapped');
  });

  $('body').on('tap', 'ul.stream li.feed', function(e){
    e.preventDefault();
    
    if (e.target.nodeName === 'A' || $(e.target).parent()[0].nodeName === 'A') {
      return false;
    }
    
    var url = $(this).attr('id').replace('post-', '/feed/');
    
    if (url == window.location.pathname) {
      return false;
    }
    
    var data = btoa(JSON.stringify({'title': 'Post', 'url': url}));
    console.log(url);
    console.log('jupo://open_link?data=' + data);
    
    open_custom_url_in_iframe('jupo://open_link?data=' + data);
    
    return false;
  });  
  
  $('body').on('tap', 'div.overview[data-href]', function(e){
    e.preventDefault();
    
    var url = $(this).data('href');
    var title = $(this).data('title');
    var data = btoa(JSON.stringify({'title': title, 'url': url}));
    console.log(url);
    console.log('jupo://open_link?data=' + data);
    
    open_custom_url_in_iframe('jupo://open_link?data=' + data);
    
          
    return false;
  });
  
  $('body').on("tap", 'li.more', function(e) {
    e.preventDefault();
    $(this).addClass('tapped');
    $('a.next', $(this)).trigger('click');
    return false;
  });
  
  
  
  $('body').on("click", 'a.next', function(e) {
    e.preventDefault();
    
    $('span.loading', this).css('display', 'inline-block');
    $('span.text', this).html('Loading...');
    
    var more_button = $(this).closest('li.more');
    
    console.log('more button clicked');
    $.ajax({
      type: "OPTIONS",
      url: $(this).attr('href'),
      success: function(html) {
        more_button.replaceWith(html);
        refresh();
      }
    });
    return false;
  });
  
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
  
  $('ul.stream').on('tap', 'a.toggle', function(e) {
    e.preventDefault();
    
    var new_class = $(this).data('class');
    var new_href = $(this).data('href');
    var new_name = $(this).data('name');
    var new_title = $(this).data('title');
    var href = $(this).attr('href');

    if (new_class != undefined) {
      $(this).data('class', $(this).attr('class'));
    }
    
    $(this).data('name', $(this).html());
    $(this).data('href', href);
    $(this).data('title', $(this).attr('title'));

    if (new_class != undefined) {
      $(this).attr('class', new_class.replace('toggle', '') + ' toggle');
    }
    $(this).html(new_name);
    $(this).attr('href', new_href);
    $(this).attr('title', new_title);
    
    if (href.indexOf('/like') != -1) {
      likes = $(this).next('span.likes');
      counter_id = '#' + likes.children('span.counter').attr('id');
      incr(counter_id, 1);
      
      if ($(counter_id).html() != '0') {
        likes.removeClass('hidden');
      } else {
        likes.addClass('hidden');
      }

    } else if (href.indexOf('/unlike') != -1) {
      likes = $(this).next('span.likes');
      counter_id = '#' + likes.children('span.counter').attr('id');
      incr(counter_id, -1);
      
      if ($(counter_id).html() != '0') {
        likes.removeClass('hidden');
      } else {
        likes.addClass('hidden');
      }
    }

    if (href != '#') {
      $.ajax({
        url: href,
        type: 'POST',
        success: function(resp) {
          console.log(resp);
          return false;
        }
      });
    }
    
    e.stopPropagation();
    return false;
  });
  
  $('ul.stream').on("tap", 'a.view-previous-comments', function(e) {
    e.preventDefault();
    
    var _this = $(this);
    var post_id = _this.parents('li.feed').attr('id');
    
    // Show preloaded comments
    $('#' + post_id + ' ul.comments li.comment.hidden').removeClass('hidden');
    
    var displayed_count = $('#' + post_id + ' ul.comments li.comment:not(.hidden)').length;
    $('.displayed-count', _this).html(displayed_count);
    
    var undisplayed_count = $('.comment-count', _this).html() - displayed_count;
    if (undisplayed_count <= 0) {
      _this.parent().remove();
    }
    else if (undisplayed_count > 5) {
      $('text', _this).html('View previous comments');
    } else {
      $('text', _this).html('View ' + undisplayed_count + ' more comments');
    }
    if (_this.attr('rel') != undefined) {
      $.ajax({
        type: "OPTIONS",
        url: _this.attr('rel'),
        dataType: "json",
        success: function(data) {
          
          if (data.next_url < 5) {
            _this.attr('rel', '#');
          } else {
            _this.attr('rel', data.next_url);
          }
          var post_id = _this.parents('li.feed').attr('id');
          $('#' + post_id + ' ul.comments li.comment:first').before(data.html);
          refresh('#' + post_id + ' ul.comments');
          return false;
        }
      });
    }
    e.stopPropagation();
    return false;
  });
  
  
  $('body').on("click", 'a', function(e) {
    e.preventDefault();
    e.stopPropagation();
    
    if ($(this).hasClass('next') || $(this).hasClass('toggle')) {
      return false;
    } 
    
    var url = $(this).attr('href');
    var data = btoa(JSON.stringify({'title': 'Post', 'url': url}));
    console.log('jupo://open_link?data=' + data);
    
    open_custom_url_in_iframe('jupo://open_link?data=' + data);
    
    return false;
  });
  

  
  
});
