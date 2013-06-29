window.whyYesIDoLikeJavaScript = function() {
  window.location = "http://play.jupo.com/jobs"
}

var msg;
var invite_messages = [
  "Ahhhh... greetings, fellow internet developer! We've been looking for you: http://play.jupo.com/jobs",
  "Do you like JavaScript too? --\> whyYesIDoLikeJavaScript()",
  "Are you here for the Profiles tab? If performance and profiling is your cup of tea, we'd love to chat! http://play.jupo.com/jobs",
  "You like to look under the hood? Why not help us build the engine? http://play.jupo.com/jobs",
  "You'll never see this printed to the console, but while you're here, why not see if you can \"shut down everything\"? Love, Andy Pham :)"
]

invite_messages.pop();
msg = Math.floor(Math.random() * invite_messages.length);
console.log(invite_messages[msg]);


var console = {};
console.log = function(){};