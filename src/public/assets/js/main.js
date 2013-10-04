jQuery(function($){
    var isIE = /*@cc_on!@*/false;

    $(window).load(function() {
        $('body').removeClass('loading');
        $('body').addClass('loaded');
    });

    // add bg header color
    $(function(){
      var _headerbg = $('.jumbo-anchor').offset().top;
      $(document).scroll(function(){
          var $this = $(this),
              pos   = $this.scrollTop();
              
          if(pos > (_headerbg - 60)){
              $('body').addClass('header-color');
          } else {
              $('body').removeClass('header-color');
          }
          if(pos < 120) {
              $('body').removeClass('header-color'); 
          }
      });
    });

    // loading animation sections
    $(function(){
        var sections = {},
            _height  = $(window).height(),
            i        = 0;
        // Grab positions of our sections 
        $('.section-anchor').each(function(){
            sections[this.name] = $(this).offset().top;
        });
        $(document).scroll(function(){
            var $this = $(this),
                pos   = $this.scrollTop();
                
            for(i in sections){
                if(sections[i] > pos && sections[i] < pos + _height){
                    $('#load_' + i).addClass('loaded');
                }  
            }
        });
    });

    // round img
    $(".round-img").load(function() {
        $(this).wrap(function(){
          return '<span class="' + $(this).attr('class') + '" style="background:url(' + $(this).attr('src') + ') no-repeat center center;" />';
        });
        $(this).css("opacity","0");
    });

    // scroll to top
    $(window).scroll(function(){
        if ($(this).scrollTop() > 100) {
            $('.scrollup').fadeIn();
        } else {
            $('.scrollup').fadeOut();
        }
    }); 
    $('.scrollup').click(function(){
        $("html, body").animate({ scrollTop: 0 }, 600);
        return false;
    });

    // placeholder fix all browsers
    /*
	$('[placeholder]').focus(function() {
      var input = $(this);
      if (input.val() == input.attr('placeholder')) {
        input.val('');
        input.removeClass('placeholder');
      }
    }).blur(function() {
      var input = $(this);
      if (input.val() == '' || input.val() == input.attr('placeholder')) {
        input.addClass('placeholder');
        input.val(input.attr('placeholder'));
      }
    }).blur();
	*/
});