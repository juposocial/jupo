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
});