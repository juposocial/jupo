
  
function open_custom_url_in_iframe(src) {
  var rootElm = document.documentElement;
  var newFrameElm = document.createElement("iframe");
  newFrameElm.setAttribute("src", src);
  rootElm.appendChild(newFrameElm);
  newFrameElm.parentNode.removeChild(newFrameElm);
}


function reload() {
  $('div.loading').show().animate({opacity: 1}, 20);
  $.ajax({
    type: 'OPTIONS',
    url: window.location.href,
    success: function(data) {
      $('body > ul.stream').html(data);
      
      refresh();
      
      $('div.loading').animate({opacity: 0}, 20, function () {
        $(this).hide();
      });
      
      console.log('refresh: done');
    }
  });
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
});