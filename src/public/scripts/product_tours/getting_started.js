// Define the tour!
var tour = {
  id: "welcome_tour",
  steps: [
    {
      title: "My Header",
      content: "This is the header of my page.",
      target: "logo",
      placement: "bottom"
    },
    {
      title: "Navigate around Jupo",
      content: "Use this menu to visit your Messages, Notes, Files, and more.",
      target: 'main-nav',
      placement: "right",
      yOffset: 150,
    },
    {
      title: "Recent Groups",
      content: "Here is where I put my content.",
      target: 'groups-nav',
      placement: "right"
    },
    {
      title: "Friends Online",
      content: "Here is where I put my content.",
      target: 'friends-online',
      placement: "right",
      yOffset: -10,
    },
    {
      title: "Menu",
      content: "Here is where I put my content.",
      target: document.querySelector("#menu a.user"),
      placement: "bottom"
    },
    {
      title: "Notification Center",
      content: "Notifications have a new icon and sit up here.",
      target: document.querySelector("#menu a.view-notifications"),
      placement: "bottom",
      xOffset: -230,
      arrowOffset: 230,
    },
    {
      title: "Share what's new",
      content: "Tell the world what's on your mind",
      target: document.querySelector("#new-feed"),
      placement: "bottom",
    },
    {
      title: "Like, share and post comments",
      content: "Here is where I put my content.",
      target: document.querySelector("li.feed footer div.actions .lfloat"),
      placement: "top",
    },
    {
      title: "Seen by",
      content: "Here is where I put my content.",
      target: document.querySelector("li.feed footer div.actions .rfloat"),
      placement: "top",
    }
  ]
};
