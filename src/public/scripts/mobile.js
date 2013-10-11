$(document).ready(function() {
  
  
  $('a').on('touchstart', function(e){
    $(this).addClass('tapped');
  });
  
  $('a').on('touchend', function(e){
    $(this).removeClass('tapped');
  });
 
  $('a').on('tap', function(e){
    e.preventDefault();
    
    // do your thing
          
    return false;
  });
  
  
  // Disable embeded youtube videos
  $('section iframe').remove();
  
  
  $('a.next').on("tap", function(e) {
    e.preventDefault();
    
    $('span.loading', this).css('display', 'inline-block');
    $('span.text', this).html('Loading...');
    var more_button = $(this).parents('li');
    console.log('more button clicked');
    $.global.loading = true;
    $.ajax({
      type: "OPTIONS",
      cache: false,
      url: $(this).attr('href'),
      dataType: "html",
      success: function(html) {
        $.global.loading = false;
        more_button.replaceWith(html);
      }
    });
    return false;
  });
  
  $('#stream').on('click', 'a.toggle', function() {
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
        type: "POST",
        headers: {
          'X-CSRFToken': get_cookie('_csrf_token')
        },
        url: href,
        success: function(resp) {
          return false;
        }
      });
    }
    return false;
    
    
  });
  
});