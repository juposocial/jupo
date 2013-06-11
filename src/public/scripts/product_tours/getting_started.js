// Define the tour!
var tour = {
  id: "welcome_tour",
  steps: [
    {
      title: "My Header",
      content: "This is the header of my page.",
      target: "logo",
      placement: "bottom",
      fixedElement: true,
    },
    {
      title: "Navigate around Jupo",
      content: "Use this menu to visit your Messages, Notes, Files, and more.",
      target: 'main-nav',
      placement: "right",
      yOffset: 150,
      fixedElement: true,
    },
    {
      title: "Recent Groups",
      content: "Here is where I put my content.",
      target: 'groups-nav',
      placement: "right",
      fixedElement: true,
    },
    {
      title: "Friends Online",
      content: "Here is where I put my content.",
      target: 'friends-online',
      placement: "right",
      yOffset: -10,
      fixedElement: true,
    },
    {
      title: "Menu",
      content: "Here is where I put my content.",
      target: document.querySelector("#menu a.user"),
      placement: "bottom",
      fixedElement: true,
    },
    {
      title: "Notification Center",
      content: "Notifications have a new icon and sit up here.",
      target: document.querySelector("#menu a.view-notifications"),
      placement: "bottom",
      xOffset: -230,
      arrowOffset: 230,
      fixedElement: true,
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
      title: "People who saw this post",
      content: "Here is where I put my content.",
      target: document.querySelector("li.feed footer div.actions .rfloat"),
      placement: "top",
    }
  ]
};
