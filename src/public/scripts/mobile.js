
  
function open_custom_url_in_iframe(src) {
  var rootElm = document.documentElement;
  var newFrameElm = document.createElement("iframe");
  newFrameElm.setAttribute("src", src);
  rootElm.appendChild(newFrameElm);
  newFrameElm.parentNode.removeChild(newFrameElm);
}

$(document).ready(function() {
  
  
  $('a').on('touchstart', function(e){
    $(this).addClass('tapped');
  });
  
  $('a').on('touchend', function(e){
    $(this).removeClass('tapped');
  });
  
  $('ul#stream li.feed a').on('tap', function(e){
    e.preventDefault();
  });

  
  $('ul#stream li.feed').on('tap', function(e){
    e.preventDefault();
    
    var url = $(this).attr('id').replace('post-', '/feed/');
    var data = btoa(JSON.stringify({'title': 'Post', 'url': url}));
    console.log(url);
    console.log('jupo://open_link?data=' + data);
    
    open_custom_url_in_iframe('jupo://open_link?data=' + data);
    
          
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
});