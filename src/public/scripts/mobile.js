
  
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
    
    var url = $(this).attr('id').replace('post-', '/feed/');
    var data = btoa(JSON.stringify({'title': 'Post', 'url': url}));
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
  
  $('body').on("click", 'a:not(.next)', function(e) {
    e.preventDefault();
    
    var url = $(this).attr('href');
    var data = btoa(JSON.stringify({'title': 'Post', 'url': url}));
    console.log('jupo://open_link?data=' + data);
    
    open_custom_url_in_iframe('jupo://open_link?data=' + data);
    
    return false;
  });
  
  $("body").on("submit", 'form.new-comment', function() {
    comments_list_id = $(this).parents('ul.comments').attr('id');
    $.ajax({
      type: "POST",
      url: $(this).attr('action'),
      data: $(this).serializeArray(),
      success: function(resp) {
        $('#' + comments_list_id + " form.new-comment textarea.mention").val('').focus();
        $('#' + comments_list_id + ' div.comments-list').append(resp);
      }
    });
    return false;
  });
  
  $('body').on('keydown', 'form.new-comment textarea', function(e) {
    console.log('asdf');
    if (e.keyCode == 13) {
      _this_form = ($(this).closest("form"));
      new_comment_form = $(this).parents('form');
      new_comment_form.trigger('submit');
      return false;
    }
  });
  
  $('ul.stream').on('tap', 'a.reply', function(e){
    e.preventDefault();
    comment_id = $(this).attr('data-comment-id');
    username = $(this).data('owner-name');
    user_id = $(this).attr('data-owner-id');
    if (user_id) {
      comments_list = $(this).parents('ul.comments:first');
    } else {
      comments_list = $('ul.comments', $(this).parents('footer'));
    }
    if (comments_list.hasClass("hidden")) {
      comments_list.toggle();
    }
    e.stopPropagation();
    return false;
  });
  
});