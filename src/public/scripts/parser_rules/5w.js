
var wysihtml5ParserRules = {
  tags: {
    strong: {},
    b:      {},
    i:      {},
    em:     {},
    br:     {},
    p:      {},
    div:    {},
    span:   {},
    ul:     {},
    ol:     {},
    li:     {},
    a:      {},       
    pre:    {},
    code:   {},      
    // blockquote: {"check_attributes": {"cite": "url"}},   
    br: {"add_class": {"clear": "clear_br"}},
    h2: {"add_class": {"align": "align_text"}},
    "a": {
        "check_attributes": {
            "href": "url" // if you compiled master manually then change this from 'url' to 'href'
        },
        "set_attributes": {
            "rel": "nofollow",
            "target": "_blank"
        }
    },
  }
};