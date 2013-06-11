// Define the tour!
var tour = {
  id: "welcome_tour",
  steps: [
    {
      title: "Network Name",
      content: "Here lies the name of your network.",
      target: "logo",
      placement: "bottom",
      fixedElement: true,
    },
    {
      title: "Jupo navigation",
      content: "All the tools of Jupo.",
      target: 'main-nav',
      placement: "right",
      yOffset: 150,
      fixedElement: true,
    },
    {
      title: "Groups Section",
      content: "Check out the available groups in the network, or you can create your own ones.",
      target: 'groups-nav',
      placement: "right",
      fixedElement: true,
    },
    {
      title: "Friends Online",
      content: "Look, who from your contacts list is online.",
      target: 'friends-online',
      placement: "right",
      yOffset: -10,
      fixedElement: true,
    },
    {
      title: "Personal Place",
      content: "All your personal belongings in here: account settings, network selection, profile management...",
      target: document.querySelector("#menu a.user"),
      placement: "bottom",
      fixedElement: true,
    },
    {
      title: "Notification Center",
      content: "Red Alert :)",
      target: document.querySelector("#menu a.view-notifications"),
      placement: "bottom",
      xOffset: -230,
      arrowOffset: 230,
      fixedElement: true,
    },
    {
      title: "Share what's new",
      content: "Tell the world what's on your mind.",
      target: document.querySelector("#new-feed"),
      placement: "bottom",
    },
    {
      title: "Like, share and post comments",
      content: "Here is where I put my content.",
      target: document.querySelector("ul#stream li.feed section > footer > .actions > .lfloat"),
      placement: "top",
    },
    {
      title: "People who saw the post",
      content: "Mouse hover it to view the details.",
      target: document.querySelector("ul#stream li.feed section > footer > .actions > .rfloat"),
      placement: "top",
    }
  ]
};
