// Define the tour!
var post_a_message = {
  id: "post_a_message",
  steps: [
    {
      title: "Enter your message",
      content: "You can mention people who are on Jupo by entering the '@' sign.",
      target: document.querySelector("form#new-feed textarea.mention"),
      placement: "left",
      yOffset: -18,
      onShow: function() {
        $('form#new-feed #message textarea.mention').val('Hello Jupo :)').focus()
      }
    },
    {
      title: "Choose who to share with",
      content: "Enter group names to share with everyone in those groups, or enter names or email addresses to share with specific people.",
      target: document.querySelector("form#new-feed textarea.mention"),
      placement: "left",
      onShow: function() {
         $('form#new-feed #send-to .token-input-list input').focus()
      },
      yOffset: 12,
    },
    {
      title: "Liven up your posts",
      content: "Attach photos, documents and files.",
      target: document.querySelector("form#new-feed footer a#attach"),
      placement: "bottom",
      xOffset: -15,
    },
    {
      title: "All set?",
      content: "Click the <strong>Share</strong> button when you're ready to post.",
      target: document.querySelector("form#new-feed footer input.button"),
      placement: "left",
      yOffset: -18,
    },
  ]
}